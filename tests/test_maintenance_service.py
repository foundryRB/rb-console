from execution_fixtures import run_rows
from orchestrator.domain.model.pull_merge_result import PullMergeResult
from orchestrator.domain.model.comment_created import CommentCreated
from orchestrator.domain.model.issue_closed import IssueClosed
from orchestrator.domain.model.repository_inventory_entry import RepositoryInventoryEntry
from maintenance_fixtures import semantic_check, semantic_comment, semantic_file, semantic_issue, semantic_pr, semantic_release, semantic_review
from capability_support import observe_repo
"""The maintenance mode's service half: the source's degradation (INT-FC-R60), the
acts' gh-exactness and refusal (INT-FC-R61), the launch compilation (INT-FC-R67),
the engine's one-shot merge gate (INT-FC-R65), and the diff-as-substance rule
(INT-FC-R63)."""
from capability_support import invoke_helper
from capability_support import command_kwargs
from orchestrator.application.services.definitions import _CHECKS_TICKS, _GIT_ROLES, _RECEIPT_TICKS
import json
import re
import urllib.request
from pytest_intent import intent
from orchestrator.adapters.outbound.github.github_acts import GitHubActs
from orchestrator.adapters.outbound.github.github_maintenance_source import GitHubMaintenanceSource
from orchestrator.domain.services.delivery_launch import HEADLESS_TURN
from orchestrator.domain.services.maintenance_launch import build_maintenance_prompt
from orchestrator.adapters.outbound.argo.maintenance_launch import compile_maintenance_workflow
from capability_support import make_capabilities
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig
import pytest

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeConfig:

    def __init__(self, user='fc-git'):
        self._user = user

    def get_setting(self, name):
        from orchestrator.application.services.definitions import _GIT_ROLES
        if name == _GIT_ROLES:
            return {role: 'unit-worker' for role in ('programmer', 'reviewer', 'librarian', 'release-manager')}
        return {'name': self._user, 'user': self._user, 'configured': True}

    def list_settings(self, prefix):
        return []

    def get_secret(self, name):
        return ''

class FakeMSource:
    """A recording maintenance source with canned GitHub shapes."""

    def __init__(self, prs=None, reviews=None, checks=None, files=None, closed=None, issues=None, comments=None, bodies=None):
        self._prs = prs or []
        self._reviews = reviews or {}
        self._checks = checks or {}
        self._files = files or {}
        self._closed = closed or []
        self._issues = issues or []
        self._comments = comments or {}
        self._bodies = bodies or {}

    def open_issues(self, repo):
        return tuple(semantic_issue(record) for record in (self._issues))

    def open_prs(self, repo):
        return tuple(semantic_pr(record) for record in (self._prs))

    def closed_prs(self, repo):
        return tuple(semantic_pr(record) for record in (self._closed))

    def pr_files(self, repo, number):
        return tuple(semantic_file(record) for record in (self._files.get(number, [])))

    def pr_reviews(self, repo, number):
        return tuple(semantic_review(record) for record in (self._reviews.get(number, [])))

    def check_runs(self, repo, sha):
        return tuple(semantic_check(record) for record in (self._checks.get(sha, [])))

    def default_branch_checks(self, repo):
        return tuple(semantic_check(record) for record in ([]))

    def tags(self, repo):
        return []

    def releases(self, repo):
        return tuple(semantic_release(record) for record in ([]))

    def unreleased_subjects(self, repo):
        return []

    def issue(self, repo, number):
        body = self._bodies.get(number)
        return semantic_issue({'number': number, 'state': 'open', 'body': body or ''})

    def pr(self, repo, number):
        pr = next((p for p in self._prs if p.get('number') == number), {})
        return semantic_pr(pr)

    def issue_comments(self, repo, number):
        return tuple(semantic_comment(record) for record in (self._comments.get(number, [])))

class FakeActs:

    def __init__(self):
        self.merged = []
        self.comments = []
        self.closed = []
        self.labels = []

    def label(self, repo, number, label):
        self.labels.append((repo, number, label))
        return None

    def merge(self, repo, number, *, expected_head=''):
        self.merged.append((repo, number))
        return PullMergeResult(True)

    def comment(self, repo, number, body):
        self.comments.append((repo, number, body))
        return CommentCreated(1)

    def close_issue(self, repo, number):
        self.closed.append((repo, number))
        return IssueClosed(number)

class FakeWorkflows:

    def __init__(self, status='Succeeded'):
        self._status = status
        self.submitted = []

    def submit(self, workflow, *, delegated_grant_id=None):
        from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
        assert isinstance(workflow, CompiledWorkflow)
        payload = json.loads(workflow.executor_payload)
        if delegated_grant_id:
            payload["metadata"].setdefault("annotations", {})["foundry-console/delegated-grant"] = json.dumps({"grant_id": delegated_grant_id})
        self.submitted.append(payload)
        return f'wf-{len(self.submitted)}'

    def status(self, handle):
        return self._status

    def list_runs(self):
        return []

    def logs(self, handle, tail=400):
        return ''

class FakeCredentials:

    def __init__(self, persisted=False):
        self._persisted = persisted

    def put(self, run_id, credential):
        return f'fc-run-{run_id}'

    def run_ref(self, run_id):
        return f'fc-run-{run_id}'

    def delivery_ref(self, slug):
        return f'fc-delivery-{slug}'

    def has_delivery(self, slug):
        return self._persisted

def _pr(n, author='fc-git', head='fix/7-x', sha='a' * 40, title='fix: x (#7)'):
    return {'state': 'open', 'number': n, 'title': title, 'user': {'login': author}, 'head': {'ref': head, 'sha': sha}, 'html_url': f'http://x/pull/{n}', 'body': 'Closes #7'}

def _posted_as(body):
    """The review state review-pr posts a body's verdict as (REF-Maintenance section 5): a
    PASS rides an approval, a FAIL a request-changes, and anything else a plain comment."""
    words = re.findall('VERDICT:\\s*(PASS|FAIL|UNRECORDED)', body or '', re.IGNORECASE)
    last = words[-1].upper() if words else ''
    return {'PASS': 'APPROVED', 'FAIL': 'CHANGES_REQUESTED'}.get(last, 'COMMENTED')
_POSTED = object()

def _rev(body, author='fc-review', at='t', assoc='MEMBER', state=_POSTED):
    """A review as GitHub returns it. Production's shape: the reviewer identity is a
    different account from the resolver that opened the PR (INT-FC-R88), holds write
    access, and posts its verdict as the review state section 5 records it as - the three
    things the verdict rule reads (INT-FC-R66). ``state`` overrides the posted one."""
    return {'user': {'login': author}, 'body': body, 'submitted_at': at, 'author_association': assoc, 'state': _posted_as(body) if state is _POSTED else state}

@intent('INT-FC-R60')
def test_source_degrades_to_empty_without_credential_or_api(monkeypatch):
    src = GitHubMaintenanceSource('org', lambda: '')
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
    with pytest.raises(SourceUnavailable):
        src.open_issues('app')
    with pytest.raises(SourceUnavailable):
        src.open_prs('app')
    with pytest.raises(SourceUnavailable):
        src.pr_files('app', 1)
    with pytest.raises(SourceUnavailable):
        src.pr_reviews('app', 1)
    with pytest.raises(SourceUnavailable):
        src.check_runs('app', 'sha')
    with pytest.raises(SourceUnavailable):
        src.tags('app')
    with pytest.raises(SourceUnavailable):
        src.releases('app')
    with pytest.raises(SourceUnavailable):
        src.unreleased_subjects('app')
    with pytest.raises(SourceUnavailable):
        src.issue('app', 1)

    def boom(*a, **k):
        raise OSError('api away')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: boom(request, timeout=timeout))
    src2 = GitHubMaintenanceSource('org', lambda: 'tok')
    with pytest.raises(SourceUnavailable):
        src2.open_prs('app')
    with pytest.raises(SourceUnavailable):
        src2.issue('app', 1)

@intent('INT-FC-R61')
def test_acts_are_gh_exact_under_fc_git_and_refuse_without_credential(monkeypatch):
    sent = []

    class FakeResp:
        headers = {}
        status = 200

        def read(self, *_size):
            return b'{"merged": true, "id": 1}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def capture(req, timeout=0):
        sent.append(req)
        return FakeResp()
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: capture(request, timeout=timeout))
    acts = GitHubActs('org', lambda: 'tok')
    acts.merge('app', 12)
    req = sent[-1]
    assert req.full_url == 'https://api.github.com/repos/org/app/pulls/12/merge'
    assert req.get_method() == 'PUT'
    assert json.loads(req.data) == {'merge_method': 'rebase'}
    assert req.headers['Authorization'] == 'Bearer tok'
    acts.comment('app', 7, 'hello')
    req = sent[-1]
    assert req.full_url == 'https://api.github.com/repos/org/app/issues/7/comments'
    assert req.get_method() == 'POST'
    assert json.loads(req.data) == {'body': 'hello'}
    bare = GitHubActs('org', lambda: '')
    with pytest.raises(RuntimeError):
        bare.merge('app', 12)

@intent('INT-FC-R67')
def test_maintenance_drives_compile_in_the_delivery_launch_shape():
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)
    wf = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.GATED, cfg, run_id='m-1', credential_secret='fc-run-m-1')
    workers = [t for t in wf['spec']['templates'] if 'container' in t]
    assert len(workers) == 1
    w = workers[0]
    assert w['retryStrategy']['limit'] == 3
    assert w['activeDeadlineSeconds'] == 1800
    assert w['container']['command'] == ['/usr/local/bin/worker-entrypoint.sh']
    cred = next((e for e in w['container']['env'] if e['name'] == 'FC_MODEL_CREDENTIAL'))
    assert cred['valueFrom']['secretKeyRef']['name'] == 'fc-run-m-1'
    assert 'tok' not in json.dumps(wf)
    endpoints = next((e for e in w['container']['env'] if e['name'] == 'FC_MCP_ENDPOINTS'))
    assert endpoints['value'] == 'playbook-studio'
    assert 'resolve-ticket' in w['container']['args'][0]
    assert '#7' in w['container']['args'][0]
    tkt = next((e for e in w['container']['env'] if e['name'] == 'FC_TICKET'))
    assert tkt['value'] == '7'
    assert next((e for e in w['container']['env'] if e['name'] == 'FC_MAINT_MODE'))['value'] == 'gated'
    assert next((e for e in w['container']['env'] if e['name'] == 'FC_MODE'))['value'] == 'interactive'
    prompt = w['container']['args'][0].lower()
    assert 'background' in prompt and 'never end the run with nothing pushed' in prompt
    one = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.ONE_SHOT, cfg, run_id='m-2')
    one_workers = [t for t in one['spec']['templates'] if 'container' in t]
    assert [w['name'] for w in one_workers] == ['worker-resolve', 'worker-review']
    blob = json.dumps(one['spec'])
    assert all(('merge' not in t['name'] for t in one['spec']['templates']))
    assert 'gh pr merge' not in blob and '/merge' not in blob
    assert all(('Never merge' in w['container']['args'][0] for w in one_workers))
    direct = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.DIRECT, cfg, run_id='m-3')
    dw = [t for t in direct['spec']['templates'] if 'container' in t]
    assert len(dw) == 1 and 'DIRECT mode' in dw[0]['container']['args'][0]
    assert next((e for e in dw[0]['container']['env'] if e['name'] == 'FC_TICKET'))['value'] == '7'
    assert next((e for e in dw[0]['container']['env'] if e['name'] == 'FC_MAINT_MODE'))['value'] == 'direct'
    check = compile_maintenance_workflow('org/app', 'reconcile-docs', None, MaintenanceMode.GATED, cfg, run_id='m-4')
    cw = [t for t in check['spec']['templates'] if 'container' in t]
    assert len(cw) == 1 and 'reconcile-docs' in cw[0]['container']['args'][0]
    assert next((e for e in cw[0]['container']['env'] if e['name'] == 'FC_TICKET'))['value'] == ''
    with pytest.raises(ValueError):
        compile_maintenance_workflow('org/app', 'deploy', None, MaintenanceMode.GATED, cfg, run_id='m-5')

@intent('INT-FC-R78')
def test_every_maintenance_worker_prompt_runs_interaction_auto():
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)

    def prompts(act, target, mode):
        wf = compile_maintenance_workflow('org/app', act, target, mode, cfg, run_id='m-a')
        return [t['container']['args'][0] for t in wf['spec']['templates'] if 'container' in t]
    for act, target, mode in [('resolve', 7, MaintenanceMode.GATED), ('resolve', 7, MaintenanceMode.DIRECT), ('review', 7, MaintenanceMode.GATED), ('reconcile-docs', None, MaintenanceMode.GATED)]:
        ps = prompts(act, target, mode)
        assert ps and all(('interaction=auto' in p.lower() and 'no human is reachable' in p.lower() for p in ps))
    one = prompts('resolve', 7, MaintenanceMode.ONE_SHOT)
    assert len(one) == 2 and all(('interaction=auto' in p.lower() for p in one))

@intent('INT-FC-R123')
def test_every_maintenance_worker_prompt_forbids_a_co_author_trailer():
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)

    def prompts(act, target, mode):
        wf = compile_maintenance_workflow('org/app', act, target, mode, cfg, run_id='m-a')
        return [t['container']['args'][0] for t in wf['spec']['templates'] if 'container' in t]
    for act, target, mode in [('resolve', 7, MaintenanceMode.GATED), ('resolve', 7, MaintenanceMode.DIRECT), ('review', 7, MaintenanceMode.GATED), ('reconcile-docs', None, MaintenanceMode.GATED), ('resolve', 7, MaintenanceMode.ONE_SHOT)]:
        ps = prompts(act, target, mode)
        assert ps and all(('co-authored-by' in p.lower() for p in ps))
        assert all(('no co-author or ai-attribution trailer' in p.lower() for p in ps))

@intent('INT-FC-R158')
def test_every_maintenance_resolve_prompt_forbids_parking_on_a_background_job():
    for mode in (MaintenanceMode.GATED, MaintenanceMode.DIRECT, MaintenanceMode.ONE_SHOT):
        for feedback in ('', 'the header still collapses on narrow screens'):
            low = build_maintenance_prompt('resolve', 'org/app', 7, mode, feedback).lower()
            assert HEADLESS_TURN.lower() in low
            assert 'must actually exist when you stop' in low

def _service(msource, macts, workflows, user='fc-git'):
    return make_capabilities(FakeRepos(), workflows=workflows, credentials=FakeCredentials(), config=FakeConfig(user), msource=msource, macts=macts)

@intent('INT-FC-R66')
def test_the_judge_never_merges_on_a_pass_by_the_identity_it_merges_as():

    class MergerConfig(FakeConfig):

        def get_setting(self, name):
            if name == _GIT_ROLES:
                return {**super().get_setting(name), 'console': 'Console Bot'}
            return super().get_setting(name)

        def list_settings(self, prefix):
            return [{'name': 'Console Bot', 'login': 'FC-Console'}]
    green = [{'status': 'completed', 'conclusion': 'success'}]
    acts = FakeActs()
    svc = make_capabilities(FakeRepos(), workflows=FakeWorkflows('Succeeded'), credentials=FakeCredentials(), config=MergerConfig(), msource=FakeMSource(prs=[_pr(12)], reviews={12: [_rev('ok\nVERDICT: PASS', author='fc-console')]}, checks={'a' * 40: green}), macts=acts)
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == []
    assert [e['result'] for e in svc.refresh.observations.oneshot.values()] == ['parked: PR #12 verdict unrecorded, checks green']

@intent('INT-FC-R65')
def test_engine_merges_on_recorded_pass_with_green_checks_and_parks_everything_else():
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [_rev('ok\nVERDICT: PASS')]}
    acts = FakeActs()
    svc = _service(FakeMSource(prs=[_pr(12, head='fix/7-x')], reviews=passing, checks={'a' * 40: green}), acts, FakeWorkflows('Succeeded'))
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == [('org/app', 12)]
    failing = {12: [_rev('no\nVERDICT: FAIL')]}
    acts2 = FakeActs()
    svc2 = _service(FakeMSource(prs=[_pr(12)], reviews=failing, checks={'a' * 40: green}), acts2, FakeWorkflows('Succeeded'))
    svc2.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc2, '_judge_oneshot_runs')
    assert acts2.merged == []
    assert any(('FAIL' in e['result'] for e in svc2.refresh.observations.oneshot.values()))
    red = [{'status': 'completed', 'conclusion': 'failure'}]
    acts3 = FakeActs()
    svc3 = _service(FakeMSource(prs=[_pr(12)], reviews=passing, checks={'a' * 40: red}), acts3, FakeWorkflows('Succeeded'))
    svc3.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc3, '_judge_oneshot_runs')
    assert acts3.merged == []
    acts4 = FakeActs()
    svc4 = _service(FakeMSource(prs=[_pr(12)], reviews={}, checks={'a' * 40: green}), acts4, FakeWorkflows('Succeeded'))
    svc4.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc4, '_judge_oneshot_runs')
    assert acts4.merged == []
    unrecorded = {12: [_rev('No findings.\n\nVERDICT: UNRECORDED', author='fc-git')]}
    acts9, wf9 = (FakeActs(), FakeWorkflows('Succeeded'))
    svc9 = _service(FakeMSource(prs=[_pr(12)], reviews=unrecorded, checks={'a' * 40: green}), acts9, wf9)
    svc9.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc9, '_judge_oneshot_runs')
    assert acts9.merged == []
    assert len(wf9.submitted) == 1
    assert [e['result'] for e in svc9.refresh.observations.oneshot.values()] == ['parked: PR #12 verdict unrecorded, checks green']
    spoofed = {12: [_rev('VERDICT: PASS', author='rando', assoc='NONE')]}
    acts6 = FakeActs()
    svc6 = _service(FakeMSource(prs=[_pr(12)], reviews=spoofed, checks={'a' * 40: green}), acts6, FakeWorkflows('Succeeded'))
    svc6.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc6, '_judge_oneshot_runs')
    assert acts6.merged == []
    for body in ('ok\nVERDICT: PASS', 'no\nVERDICT: FAIL'):
        for state in ('COMMENTED', 'DISMISSED'):
            acts10, wf10 = (FakeActs(), FakeWorkflows('Succeeded'))
            stated = {12: [_rev(body, state=state)]}
            svc10 = _service(FakeMSource(prs=[_pr(12)], reviews=stated, checks={'a' * 40: green}), acts10, wf10)
            svc10.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
            invoke_helper(svc10, '_judge_oneshot_runs')
            assert acts10.merged == []
            assert len(wf10.submitted) == 1
            assert [e['result'] for e in svc10.refresh.observations.oneshot.values()] == ['parked: PR #12 verdict awaiting, checks green']
    contradicted = {12: [_rev('ok\nVERDICT: PASS', at='2026-07-14T10:00:00Z'), _rev('no\nVERDICT: FAIL', at='2026-07-14T11:00:00Z', state='APPROVED')]}
    acts11, wf11 = (FakeActs(), FakeWorkflows('Succeeded'))
    svc11 = _service(FakeMSource(prs=[_pr(12)], reviews=contradicted, checks={'a' * 40: green}), acts11, wf11)
    svc11.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc11, '_judge_oneshot_runs')
    assert acts11.merged == []
    assert len(wf11.submitted) == 1
    assert [e['result'] for e in svc11.refresh.observations.oneshot.values()] == ['parked: PR #12 FAILed and no persisted credential to re-drive']
    acts5 = FakeActs()
    svc5 = _service(FakeMSource(prs=[_pr(12, author='colleague')], reviews=passing, checks={'a' * 40: green}), acts5, FakeWorkflows('Succeeded'))
    svc5.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc5, '_judge_oneshot_runs')
    assert acts5.merged == [('org/app', 12)]

    class Refusing(FakeActs):

        def merge(self, repo, number, *, expected_head=''):
            raise RuntimeError('branch protection: review required')
    acts8 = Refusing()
    svc8 = _service(FakeMSource(prs=[_pr(12)], reviews=passing, checks={'a' * 40: green}), acts8, FakeWorkflows('Succeeded'))
    svc8.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc8, '_judge_oneshot_runs')
    assert acts8.merged == []
    assert any(('branch protection' in e['result'] for e in svc8.refresh.observations.oneshot.values()))
    acts7 = FakeActs()
    stray = _pr(13, head='release/7-rc', title='release 7 rc')
    stray['body'] = 'cutting the rc'
    svc7 = _service(FakeMSource(prs=[stray], reviews={}, checks={'a' * 40: green}), acts7, FakeWorkflows('Succeeded'))
    svc7.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc7, '_judge_oneshot_runs')
    assert acts7.merged == []
    assert any(('no open PR' in e['result'] for e in svc7.refresh.observations.oneshot.values()))

@intent('INT-FC-R65')
def test_judge_ledger_is_derived_so_a_restart_cannot_orphan_a_drive():
    """The proof run lived this: a rollout replaced the pod mid-drive and the
    in-memory ledger died with it. The judge now re-derives its pending set from
    the executor's labeled runs - same tick, same merge, no memory required."""
    from types import SimpleNamespace
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [_rev('ok\nVERDICT: PASS')]}

    class LabeledRuns(FakeWorkflows):

        def list_runs(self):
            return run_rows([{'kind': 'maintenance', 'handle': 'live:workflow.argoproj.io/maint-resolve-app-x1', 'name': 'maint-resolve-app-x1', 'maintenance': 'resolve', 'mode': 'one-shot', 'ticket': '7', 'repo': 'org/app', 'repo_slug': 'app', 'phase': 'Succeeded'}])
    acts = FakeActs()
    svc = _service(FakeMSource(prs=[_pr(12)], reviews=passing, checks={'a' * 40: green}), acts, LabeledRuns('Succeeded'))
    svc.refresh.observations.fleet = [SimpleNamespace(name='app', repo='org/app')]
    assert svc.refresh.observations.oneshot == {}
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == [('org/app', 12)]

@intent('INT-FC-R65')
def test_judge_ledger_matches_a_mixed_case_repo_slug():
    """The run's repo-slug label is lowercased ('solveos'), but FleetItem.name is the
    case-preserving GitHub name ('SolveOS'); a raw match orphaned the drive after a restart
    (the recorded PASS never merged). Normalizing both sides re-derives and merges."""
    from types import SimpleNamespace
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [_rev('ok\nVERDICT: PASS')]}

    class LabeledRuns(FakeWorkflows):

        def list_runs(self):
            return run_rows([{'kind': 'maintenance', 'handle': 'live:maint-resolve-solveos-x1', 'name': 'maint-resolve-solveos-x1', 'maintenance': 'resolve', 'mode': 'one-shot', 'ticket': '7', 'repo': 'org/SolveOS', 'repo_slug': 'solveos', 'phase': 'Succeeded'}])
    acts = FakeActs()
    svc = _service(FakeMSource(prs=[_pr(12)], reviews=passing, checks={'a' * 40: green}), acts, LabeledRuns('Succeeded'))
    svc.refresh.observations.fleet = [SimpleNamespace(name='SolveOS', repo='org/SolveOS')]
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == [('org/SolveOS', 12)]

@intent('INT-FC-R85')
def test_every_driven_review_ends_on_one_of_review_prs_three_verdicts():
    """The standalone review and a one-shot resolve's inline review both end as review-pr
    does: PASS, FAIL, or UNRECORDED when the reviewing identity is the PR's author or the
    merger - never told PASS or FAIL are the only lines it may write."""
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)
    one = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.ONE_SHOT, cfg, run_id='m-2')
    inline = next((t for t in one['spec']['templates'] if t['name'] == 'worker-review'))['container']['args'][0]
    standalone = build_maintenance_prompt('review', 'org/app', 12, MaintenanceMode.GATED)
    for prompt in (inline, standalone):
        assert '`VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: UNRECORDED`' in prompt
        assert "PR's author or the merger" in prompt
        assert 'exactly `VERDICT: PASS` or `VERDICT: FAIL`' not in prompt

@intent('INT-FC-R85')
def test_oneshot_resolve_stamps_each_step_with_its_own_phase():
    """The one-shot resolve's two workers must carry their OWN completeness phase - the resolve
    step maintenance:resolve, the review step maintenance:review - not both maintenance:resolve,
    or the review step validates the resolve's PR instead of a posted verdict."""
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)
    one = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.ONE_SHOT, cfg, run_id='m-2')
    workers = {t['name']: t for t in one['spec']['templates'] if 'container' in t}

    def phase_of(name):
        return next((e['value'] for e in workers[name]['container']['env'] if e['name'] == 'FC_PHASE'))
    assert phase_of('worker-resolve') == 'maintenance:resolve'
    assert phase_of('worker-review') == 'maintenance:review'

@intent('INT-FC-R65')
def test_judge_reports_already_merged_not_parked_after_a_merge():
    """A one-shot run re-derived after its PR merged (e.g. a pod restart) must read 'already
    merged', not a misleading 'parked: no open PR'."""
    from types import SimpleNamespace
    merged = {'number': 14, 'merged_at': 't', 'head': {'ref': 'feat/7-x'}, 'title': 'feat(#7): x', 'body': 'Closes #7'}

    class LabeledRuns(FakeWorkflows):

        def list_runs(self):
            return run_rows([{'kind': 'maintenance', 'handle': 'h1', 'name': 'maint-resolve-app-x1', 'maintenance': 'resolve', 'mode': 'one-shot', 'ticket': '7', 'repo': 'org/app', 'repo_slug': 'app', 'phase': 'Succeeded'}])
    src = FakeMSource(prs=[], closed=[merged])
    svc = _service(src, FakeActs(), LabeledRuns('Succeeded'))
    svc.refresh.observations.fleet = [SimpleNamespace(name='app', repo='org/app')]
    invoke_helper(svc, '_judge_oneshot_runs')
    assert 'already merged PR #14' in next(iter(svc.refresh.observations.oneshot.values()))['result']

@intent('INT-FC-R82')
def test_observed_maintenance_run_heads_the_inbox_and_folds_its_open_ticket():
    from dataclasses import asdict
    from types import SimpleNamespace
    from orchestrator.application.services.projections.compute_inbox import helper_compute_inbox

    repo = 'org/SolveOS'
    svc = _service(FakeMSource(issues=[{'number': 7, 'title': 'Fix the defect'}]), FakeActs(), FakeWorkflows())
    observations = svc.refresh.observations
    observations.fleet = [SimpleNamespace(repo=repo, name='SolveOS', hidden=False)]
    positions = svc.maintenance_positions.execute(repo)
    observations.metadata[repo] = {'maintenance_state': {'positions': asdict(positions)}}
    observations.runs = run_rows([{'kind': 'maintenance', 'handle': 'live/run', 'name': 'opaque-name', 'maintenance': 'resolve', 'ticket': '7', 'repo': repo, 'phase': 'Running'}])
    inbox = helper_compute_inbox(observations=observations)
    assert inbox[0]['signal'] == 'running'
    assert inbox[0]['repo'] == repo and inbox[0]['number'] == 7
    assert not any(item['signal'] == 'issue' and item['number'] == 7 for item in inbox)
    observations.runs = run_rows([{'kind': 'maintenance', 'handle': 'foreign', 'name': 'opaque-name', 'maintenance': 'resolve', 'ticket': '7', 'repo': 'other/SolveOS', 'phase': 'Running'}])
    inbox = helper_compute_inbox(observations=observations)
    assert any(item['signal'] == 'issue' and item['repo'] == repo and item['number'] == 7 for item in inbox)

@intent('INT-FC-R86')
def test_maintenance_close_ticket_closes_the_issue():
    """A merged PR that did not auto-close its ticket: the Close-ticket act closes the issue
    (gh issue close), so the loop finishes instead of a meaningless re-drive."""
    acts = FakeActs()
    svc = _service(FakeMSource(), acts, FakeWorkflows())
    svc.maintenance_close_ticket.execute('org/app', 7, **command_kwargs('org/app'))
    assert acts.closed == [('org/app', 7)]

@intent('INT-FC-R100')
def test_maintenance_switch_to_delivery_reads_the_prompt_and_hides_the_ticket():
    """Switching an over-scope ticket to a delivery line (issue #13) reads the prepared delivery
    prompt back off the ticket's marked comment (or the ticket's own body when no comment carries
    the marker) and hides the ticket with foundry-hidden - so the Delivery form pre-fills with the
    prepared brief and the concern reads once, as a line."""
    marker = '<!-- foundry:delivery-prompt -->'
    comments = {13: [{'body': 'unrelated chatter'}, {'body': f'{marker}\nBuild the billing module: line items, invoices, tax.'}]}
    acts = FakeActs()
    svc = _service(FakeMSource(comments=comments), acts, FakeWorkflows())
    out = svc.maintenance_switch_to_delivery.execute('org/app', 13, **command_kwargs('org/app'))
    assert out['prompt'] == 'Build the billing module: line items, invoices, tax.'
    assert out['hidden'] is True
    assert acts.labels == [('org/app', 13, 'foundry-hidden')]
    acts2 = FakeActs()
    svc2 = _service(FakeMSource(comments={13: [{'body': 'just a note'}]}, bodies={13: '  Build the billing module.\n'}), acts2, FakeWorkflows())
    out2 = svc2.maintenance_switch_to_delivery.execute('org/app', 13, **command_kwargs('org/app'))
    assert out2['prompt'] == 'Build the billing module.'
    assert acts2.labels == [('org/app', 13, 'foundry-hidden')]
    acts3 = FakeActs()
    svc3 = _service(FakeMSource(comments=comments, bodies={13: 'the raw ask'}), acts3, FakeWorkflows())
    assert svc3.maintenance_switch_to_delivery.execute('org/app', 13, **command_kwargs('org/app'))['prompt'] == 'Build the billing module: line items, invoices, tax.'
    acts4 = FakeActs()
    svc4 = _service(FakeMSource(comments={13: [{'body': 'just a note'}]}), acts4, FakeWorkflows())
    out4 = svc4.maintenance_switch_to_delivery.execute('org/app', 13, **command_kwargs('org/app'))
    assert out4['prompt'] == ''
    assert acts4.labels == [('org/app', 13, 'foundry-hidden')]

@intent('INT-FC-R100')
def test_maintenance_state_excludes_foundry_hidden_tickets_from_the_pane_by_default():
    """The other half of the switch: adding foundry-hidden must actually remove the ticket from
    the maintenance pane's backlog (issue #13, "the ticket leaves the loop"), not just from the
    Fleet Inbox. The pane's state excludes foundry-hidden tickets by default and reveals them on
    include_hidden - the issue-scope mirror of the Fleet's hide, extended to the pane."""
    hidden = {'number': 7, 'title': 'switched to a delivery line', 'user': {'login': 'rafael'}, 'labels': [{'name': 'foundry-delivery-scale'}, {'name': 'foundry-hidden'}], 'html_url': 'http://x/7'}
    plain = {'number': 9, 'title': 'a normal ticket', 'user': {'login': 'rafael'}, 'labels': [], 'html_url': 'http://x/9'}
    svc = _service(FakeMSource(issues=[hidden, plain]), FakeActs(), FakeWorkflows())
    shown = {i['number'] for i in observe_repo(svc, 'org/app').maintenance_state.execute('org/app')['positions']['issues']}
    assert shown == {9}
    everything = {i['number'] for i in observe_repo(svc, 'org/app').maintenance_state.execute('org/app', include_hidden=True)['positions']['issues']}
    assert everything == {7, 9}

class FakeOrgSource:
    def scan(self):
        return []

    """The fleet-scan half the inbox sweep reads: one org repo, so a full refresh()
    derives a real inbox instead of the empty one a missing `source` yields."""

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='org/app', name='app', updated_at=None, topics=(), repository_id='')]

@intent('INT-FC-R96')
def test_maintenance_inbox_excludes_foundry_hidden_tickets_by_default():
    hidden = {'number': 7, 'title': 'noise-free wontfix', 'user': {'login': 'rafael'}, 'labels': [{'name': 'foundry-hidden'}], 'html_url': 'http://x/7'}
    plain = {'number': 9, 'title': 'plain ticket', 'user': {'login': 'rafael'}, 'labels': [], 'html_url': 'http://x/9'}
    svc = make_capabilities(FakeRepos(), source=FakeOrgSource(), credentials=FakeCredentials(), config=FakeConfig(), msource=FakeMSource(issues=[hidden, plain]), macts=FakeActs())
    svc.refresh.execute()
    shown = {it['number'] for it in svc.maintenance_inbox.execute()['items'] if it['signal'] == 'issue'}
    assert shown == {9}
    everything = {it['number'] for it in svc.maintenance_inbox.execute(include_hidden=True)['items'] if it['signal'] == 'issue'}
    assert everything == {7, 9}

class FakeHiddenOrgSource:
    def scan(self):
        return []

    """Two org repos, one carrying the 'foundry-hidden' topic: the noise repo (a CI mirror,
    a vendored library) an operator deliberately took off the Fleet board."""

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='org/app', name='app', updated_at=None, topics=(), repository_id=''), RepositoryInventoryEntry(repository='org/ci', name='ci', updated_at=None, topics=('foundry-hidden',), repository_id='')]

class RedBranchMSource(FakeMSource):
    """Every repo's default branch is red - the live signal the topic hide had no answer
    for: five hidden repos filing red-ci rows the operator could neither clear nor dismiss."""

    def default_branch_checks(self, repo):
        return (semantic_check({'status': 'completed', 'conclusion': 'failure'}),)

@intent('INT-FC-R155')
def test_maintenance_inbox_excludes_every_row_of_a_foundry_hidden_repo_by_default():
    """The repo-topic hide at inbox scope. The label hide answers for one ticket by design
    (INT-FC-R96), so a hidden repo's red-ci, drift and unreleased rows kept queueing while the
    repo itself sat off the Fleet. Every row of a hidden repo is now marked and excluded by
    default - and MARKED, never dropped, so 'show hidden' reveals it with no re-derivation."""
    ticket = {'number': 9, 'title': 'plain ticket', 'user': {'login': 'rafael'}, 'labels': [], 'html_url': 'http://x/9'}
    svc = make_capabilities(FakeRepos(), source=FakeHiddenOrgSource(), credentials=FakeCredentials(), config=FakeConfig(), msource=RedBranchMSource(issues=[ticket]), macts=FakeActs())
    svc.refresh.execute()
    shown = svc.maintenance_inbox.execute()['items']
    assert {it['repo'] for it in shown} == {'org/app'}
    assert {it['signal'] for it in shown} == {'red-ci', 'issue'}
    everything = svc.maintenance_inbox.execute(include_hidden=True)['items']
    assert {it['repo'] for it in everything} == {'org/app', 'org/ci'}
    hidden_rows = [it for it in everything if it['repo'] == 'org/ci']
    assert {it['signal'] for it in hidden_rows} == {'red-ci', 'issue'}
    assert all((it['hidden'] is True for it in hidden_rows))
    assert all((it['hidden'] is False for it in everything if it['repo'] == 'org/app'))

def test_drive_folds_the_persisted_delivery_credential():
    """The cockpit sends no credential (the repo's saved agent backs the worker): the
    drive must fold the persisted credential in, not refuse - and still refuse when
    NEITHER source has one."""
    svc = make_capabilities(FakeRepos(), workflows=FakeWorkflows(), credentials=FakeCredentials(persisted=True), config=FakeConfig(), msource=FakeMSource(), macts=FakeActs())
    out = svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig(None, 'org/app', True), **command_kwargs('org/app'))
    assert out.handle
    bare = make_capabilities(FakeRepos(), workflows=FakeWorkflows(), credentials=FakeCredentials(persisted=False), config=FakeConfig(), msource=FakeMSource(), macts=FakeActs())
    with pytest.raises(ValueError):
        bare.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig(None, 'org/app', True), **command_kwargs('org/app'))

@intent('INT-FC-R67')
def test_maintenance_drive_honors_the_per_delivery_worker_timeout():
    """A maintenance worker carries the repo's OWN wall-clock budget, like a delivery worker
    - a flat 30 min kills a big resolve mid-flight. With none configured the 1h floor
    applies, so the submitted workers deadline at 3600s."""
    wf = FakeWorkflows()
    svc = make_capabilities(FakeRepos(), workflows=wf, credentials=FakeCredentials(persisted=True), config=FakeConfig(), msource=FakeMSource(), macts=FakeActs())
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig(None, 'org/app', True), **command_kwargs('org/app'))
    workers = [t for t in wf.submitted[-1]['spec']['templates'] if 'container' in t]
    assert workers and all((t['activeDeadlineSeconds'] == 3600 for t in workers))

def _resolve_prompt_of(wf):
    """The submitted run's resolve worker prompt (its args[0])."""
    return next((t for t in wf.submitted[-1]['spec']['templates'] if 'container' in t))['container']['args'][0]

@intent('INT-FC-R87')
def test_gated_redrive_over_a_fail_threads_the_findings_so_the_worker_revises_the_pr():
    """A resolve re-drive over a PR a fresh-eyes review already FAILed threads the reviewer's
    findings as the work order, so the worker REVISES the open PR (never opens a second one) -
    the operator-pressed twin of the one-shot engine's re-drive. The findings are DERIVED on the
    drive from the ticket's open PR; the operator (cockpit) sends no feedback."""
    findings = 'The error path is untested; add a test.\nVERDICT: FAIL'
    review = _rev(findings, at='2026-07-14T10:00:00Z')
    msource = FakeMSource(prs=[_pr(18, head='fix/7-x', title='fix: x (#7)')], reviews={18: [review]})
    wf = FakeWorkflows()
    svc = _service(msource, FakeActs(), wf)
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    prompt = _resolve_prompt_of(wf)
    assert 'Do NOT open a new PR' in prompt
    assert 'The error path is untested' in prompt
    assert 'Branch as' not in prompt

@intent('INT-FC-R87')
def test_a_first_resolve_or_a_redrive_over_a_non_failing_pr_carries_no_findings():
    """No recorded FAIL means no work order: a first resolve (no open PR) and a re-drive over an
    awaiting or passing PR both get the fresh 'open the PR' prompt, never a spurious revision."""
    wf = FakeWorkflows()
    svc = _service(FakeMSource(prs=[]), FakeActs(), wf)
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    first = _resolve_prompt_of(wf)
    assert 'Branch as' in first and 'Do NOT open a new PR' not in first
    passing = _rev('looks good\nVERDICT: PASS', at='2026-07-14T11:00:00Z')
    wf2 = FakeWorkflows()
    svc2 = _service(FakeMSource(prs=[_pr(18, head='fix/7-x', title='fix: x (#7)')], reviews={18: [passing]}), FakeActs(), wf2)
    svc2.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    over_pass = _resolve_prompt_of(wf2)
    assert 'Branch as' in over_pass and 'Do NOT open a new PR' not in over_pass

@intent('INT-FC-R63')
def test_pr_substance_carries_the_actual_diff():
    files = {12: [{'filename': 'a.py', 'status': 'modified', 'additions': 2, 'deletions': 1, 'patch': '@@ -1 +1,2 @@\n-x\n+y\n+z'}]}
    svc = _service(FakeMSource(prs=[_pr(12)], files=files), FakeActs(), FakeWorkflows())
    sub = svc.maintenance_substance.execute('org/app', 'pr', 12)
    assert sub['files'][0]['filename'] == 'a.py'
    assert '+y' in sub['files'][0]['patch']
    assert sub['url']

@intent('INT-FC-R75')
def test_oneshot_redrives_on_fail_within_budget_then_degrades():
    """A one-shot review FAIL is the reviewer's work order, not a dead end: the engine
    re-drives the resolve on the findings (revising the open PR) while the attempt budget
    holds, and degrades to the operator once it is spent. The attempt count is DERIVED
    from the ticket's runs, so a restart cannot uncap it; with no persisted credential the
    re-drive parks rather than loops."""
    from types import SimpleNamespace
    green = [{'status': 'completed', 'conclusion': 'success'}]
    failing = {12: [_rev('this only defers the ask; no implementation ships\nVERDICT: FAIL')]}

    def runs_for(n):
        return [{'kind': 'maintenance', 'handle': f'live:workflow.argoproj.io/maint-resolve-app-x{i}', 'name': f'maint-resolve-app-x{i}', 'maintenance': 'resolve', 'mode': 'one-shot', 'ticket': '7', 'repo': 'org/app', 'repo_slug': 'app', 'phase': 'Succeeded', 'created': f't{i}'} for i in range(n, 0, -1)]

    class Runs(FakeWorkflows):

        def __init__(self, n):
            super().__init__('Succeeded')
            self._n = n

        def list_runs(self):
            return run_rows(runs_for(self._n))

    def _svc(n, persisted=True):
        s = make_capabilities(FakeRepos(), workflows=Runs(n), credentials=FakeCredentials(persisted=persisted), config=FakeConfig(), macts=FakeActs(), msource=FakeMSource(prs=[_pr(12)], reviews=failing, checks={'a' * 40: green}))
        s.refresh.observations.fleet = [SimpleNamespace(name='app', repo='org/app')]
        return s
    svc = _svc(1)
    invoke_helper(svc, '_judge_oneshot_runs')
    assert len(svc.drive.workflows.submitted) == 1
    resolve_t = next((t for t in svc.drive.workflows.submitted[0]['spec']['templates'] if t.get('name') == 'worker-resolve'))
    prompt = resolve_t['container']['args'][0]
    assert 'VERDICT: FAIL' in prompt and 'Do NOT open a new PR' in prompt
    assert 'only defers the ask' in prompt
    assert any(('attempt 2/2' in e['result'] for e in svc.refresh.observations.oneshot.values()))
    assert svc.maintenance_merge.macts.merged == []
    spent = _svc(2)
    invoke_helper(spent, '_judge_oneshot_runs')
    assert spent.drive.workflows.submitted == []
    assert any(('degraded' in e['result'] and 'over to you' in e['result'] for e in spent.refresh.observations.oneshot.values()))
    svc_nc = _svc(1, persisted=False)
    invoke_helper(svc_nc, '_judge_oneshot_runs')
    assert svc_nc.drive.workflows.submitted == []
    assert any(('no persisted credential' in e['result'] for e in svc_nc.refresh.observations.oneshot.values()))

@intent('INT-FC-R119')
def test_a_ticket_holds_exactly_one_ledger_row_and_the_newest_drive_owns_it():
    """One drive per ticket, one row: a second press over a settled receipt retires it,
    so the ticket's own line reads the drive in flight and never the superseded outcome."""
    green = [{'status': 'completed', 'conclusion': 'success'}]
    svc = _service(FakeMSource(prs=[], checks={'a' * 40: green}), FakeActs(), FakeWorkflows('Succeeded'))
    cfg = RunConfig('tok', 'org/app', True)
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', cfg, **command_kwargs('org/app'))
    invoke_helper(svc, '_judge_oneshot_runs')
    settled = next(iter(svc.refresh.observations.oneshot.values()))
    assert settled['acted'] and 'no open PR' in settled['result']
    out = svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', cfg, **command_kwargs('org/app'))
    rows = [e for e in svc.refresh.observations.oneshot.values() if e['ticket'] == 7]
    assert len(rows) == 1 and list(svc.refresh.observations.oneshot) == [out.handle]
    assert not rows[0]['acted'] and rows[0]['result'] == ''
    svc.maintenance_drive.execute('org/app', 'resolve', 9, 'one-shot', cfg, **command_kwargs('org/app'))
    assert sorted((e['ticket'] for e in svc.refresh.observations.oneshot.values())) == [7, 9]

@intent('INT-FC-R119')
def test_a_fresh_run_supersedes_a_settled_row_but_never_a_drive_in_flight():
    """The ledger derived from the executor: a settled row is a receipt the ticket's newest
    run replaces (else a ticket driven again after its PR parked is never judged at all),
    while a row still in flight outranks the run list, which lags a fresh submit by a tick."""
    from types import SimpleNamespace
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [_rev('ok\nVERDICT: PASS')]}

    def _run(name):
        return {'kind': 'maintenance', 'handle': f'live:workflow.argoproj.io/{name}', 'name': name, 'maintenance': 'resolve', 'mode': 'one-shot', 'ticket': '7', 'repo': 'org/app', 'repo_slug': 'app', 'phase': 'Succeeded'}

    class Runs(FakeWorkflows):

        def __init__(self):
            super().__init__('Succeeded')
            self.rows = [_run('maint-resolve-app-x1')]

        def list_runs(self):
            return run_rows(self.rows)
    acts = FakeActs()
    src = FakeMSource(prs=[], reviews=passing, checks={'a' * 40: green})
    svc = _service(src, acts, Runs())
    svc.refresh.observations.fleet = [SimpleNamespace(name='app', repo='org/app')]
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == [] and next(iter(svc.refresh.observations.oneshot.values()))['acted']
    svc.drive.workflows.rows = [_run('maint-resolve-app-x2'), _run('maint-resolve-app-x1')]
    src._prs = [_pr(12)]
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == [('org/app', 12)]
    assert list(svc.refresh.observations.oneshot) == ['live:workflow.argoproj.io/maint-resolve-app-x2']
    svc2 = _service(FakeMSource(prs=[]), FakeActs(), Runs())
    svc2.refresh.observations.fleet = [SimpleNamespace(name='app', repo='org/app')]
    out = svc2.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc2, '_derive_oneshot_ledger')
    assert list(svc2.refresh.observations.oneshot) == [out.handle]

@intent('INT-FC-R119')
def test_one_unreadable_drive_does_not_strand_the_rest_of_the_sweep():
    """Judging is per row. A GitHub read that raises on one drive leaves that row for the
    next tick and judges every other one on this tick - a shared sweep stranded them all
    un-judged, and an un-judged row reads on the panel as a run still in flight."""
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [_rev('ok\nVERDICT: PASS')]}

    class Unreadable(FakeMSource):
        fail = False

        def open_prs(self, repo):
            if self.fail and repo == 'org/broken':
                raise RuntimeError('the PR read failed')
            return tuple(semantic_pr(record) for record in (super().open_prs(repo)))
    acts = FakeActs()
    svc = _service(Unreadable(prs=[_pr(12)], reviews=passing, checks={'a' * 40: green}), acts, FakeWorkflows('Succeeded'))
    broken = svc.maintenance_drive.execute('org/broken', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/broken', True), **command_kwargs('org/broken'))
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    svc.maintenance_drive.msource.fail = True
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == [('org/app', 12)]
    assert not svc.refresh.observations.oneshot[broken.handle]['acted']

@intent('INT-FC-R119')
def test_a_row_says_what_the_engine_is_doing_and_its_receipt_is_bounded():
    """The ledger is a pending set, not a log. A finished run waiting on CI says so (the
    panel's fallback line is for a drive the engine has said nothing about yet), and a
    settled row is retired after its bounded life - the merged PR and the ticket's runs
    on the executor are the durable record, so nothing is lost with it."""
    pending = [{'status': 'in_progress', 'conclusion': None}]
    acts = FakeActs()
    svc = _service(FakeMSource(prs=[_pr(12)], checks={'a' * 40: pending}), acts, FakeWorkflows('Succeeded'))
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc, '_judge_oneshot_runs')
    waiting = next(iter(svc.refresh.observations.oneshot.values()))
    assert not waiting['acted'] and 'waits on its checks' in waiting['result']
    for _ in range(_CHECKS_TICKS + 1):
        invoke_helper(svc, '_judge_oneshot_runs')
    settled = next(iter(svc.refresh.observations.oneshot.values()))
    assert settled['acted'] and 'parked: PR #12' in settled['result']
    for _ in range(_RECEIPT_TICKS + 1):
        invoke_helper(svc, '_judge_oneshot_runs')
    assert svc.refresh.observations.oneshot == {}

@intent('INT-FC-R58')
def test_deployed_of_reads_the_platform_status_word_as_health():
    """The positions' deployment-health half: _deployed_of reads the warm fleet cache's
    status word and folds it to True (running), False (an explicit unhealthy word) or None
    (paused / absent / a repo the fleet does not hold), so the derived train can carry a
    genuine unhealthy - the source the 'drift' inbox signal had lacked."""
    from types import SimpleNamespace
    svc = make_capabilities(FakeRepos())
    svc.refresh.observations.fleet = [SimpleNamespace(name='live', repo='org/live', live='running'), SimpleNamespace(name='off', repo='org/off', live='paused'), SimpleNamespace(name='broken', repo='org/broken', live='crashloopbackoff')]
    assert invoke_helper(svc, '_deployed_of', 'org/live') == ('running', True)
    assert invoke_helper(svc, '_deployed_of', 'org/off') == ('paused', None)
    assert invoke_helper(svc, '_deployed_of', 'org/broken') == ('crashloopbackoff', False)
    assert invoke_helper(svc, '_deployed_of', 'org/absent') == ('', None)
