from execution_fixtures import run_rows
from orchestrator.domain.model.pull_merge_result import PullMergeResult
from orchestrator.domain.model.comment_created import CommentCreated
from orchestrator.domain.model.issue_closed import IssueClosed
from maintenance_fixtures import semantic_check, semantic_comment, semantic_issue, semantic_pr, semantic_review
import json
from capability_support import observe_repo
"""Managed: a line that runs over a repository the foundry does not own (issue #130).

Managed was doctrine with no machinery - the tier was decided, its entry act existed, and
every line still assumed our own org: our credentials, our issues, our CI. This is the
maintenance half of the machinery, and the tests that matter most are the ones about WHICH
repository each half of the act reaches, because the whole failure mode is subtle: an act
that works the wrong tree, or files the fix where nobody is looking, looks like a working
run from every angle except the one that counts.

Audit: csd-intent .
"""
from capability_support import invoke_helper
from capability_support import command_kwargs
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.domain.services.maintenance_launch import PairHome, home_directive
from orchestrator.adapters.outbound.argo.maintenance_launch import compile_maintenance_workflow
from capability_support import make_capabilities
from orchestrator.domain.model.pair_credential import PairCredential
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.instantiation import Instantiation
from orchestrator.domain.promotion import derive_instantiation
from orchestrator.domain.model.run_config import RunConfig
from tests.test_maintenance_service import _posted_as

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeMaint:
    def issue_comments(self, repo, number):
        return tuple(semantic_comment(record) for record in ([]))

    def issue(self, repo, number):
        return semantic_issue({"number": number, "state": "open", "body": ""})

    def pr(self, repo, number):
        return semantic_pr({"number": number, "state": "open", "head": {"sha": "unit-head"}, "user": {"login": "author"}})

    def pr_reviews(self, repo, number):
        return tuple(semantic_review(record) for record in ([{"user": {"login": "reviewer"}, "body": "VERDICT: PASS", "state": "APPROVED", "submitted_at": "t", "author_association": "MEMBER"}]))

    def check_runs(self, repo, sha):
        return tuple(semantic_check(record) for record in ([{"status": "completed", "conclusion": "success"}]))


    def tags(self, repo):
        return ['v1.0.0']
HOME_CONTRACT = 'targets:\n  - name: acme-home\n    kind: repository\n    repo: acme/portal\n    branch: main\n    credential: acme-portal-push\n    door: pull-request\n    terms: source\n    acceptance: none\n'
ENV_CONTRACT = 'targets:\n  - name: example-prod\n    kind: environment\n    install: example\n    environment: prod\n    door: commit\n    terms: version\n    acceptance: none\n'

class FakeSource:
    """An app's own repo, as the tier derivation reads it: its contract, and whether it is
    onboarded anywhere at all."""

    def __init__(self, contract=HOME_CONTRACT, installs=None):
        self._contract = contract
        self._installs = installs if installs is not None else {}

    def repository_revision(self, repo):
        return "unit-head"

    def contract_text(self, repo, *, revision=""):
        return self._contract

    def deploy_installs(self, repo):
        return self._installs

    def environment_values(self, repo, install, environment):
        return 'tag: 1.0.0\n'

    def open_door(self, repo, base, credential=''):
        return ''

    def last_merged_release(self, repo, base, credential=''):
        return ''

    def probe(self, url):
        return True

class FakeCredentials:

    def has_delivery(self, slug):
        return True

    def run_ref(self, run_id):
        return f'fc-run-{run_id}'

    def delivery_ref(self, slug):
        return f'fc-delivery-{slug}'

    def put(self, run_id, credential):
        return f'fc-run-{run_id}'

class FakeWorkflows:

    def __init__(self):
        self.submitted = []

    def submit(self, workflow, *, delegated_grant_id=None):
        from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
        assert isinstance(workflow, CompiledWorkflow)
        payload = json.loads(workflow.executor_payload)
        if delegated_grant_id:
            payload["metadata"].setdefault("annotations", {})["foundry-console/delegated-grant"] = json.dumps({"grant_id": delegated_grant_id})
        self.submitted.append(payload)
        return 'wf-1'

class FakeActs:

    def __init__(self):
        self.merged = []

    def merge(self, repo, number, *, expected_head=''):
        self.merged.append((repo, number))
        return PullMergeResult(True)

def _svc(source=None, workflows=None, acts=None):
    return make_capabilities(FakeRepos(), workflows=workflows, credentials=FakeCredentials(), config=InMemoryConfigStore(), msource=FakeMaint(), psource=source or FakeSource(), macts=acts, door=FakeDoor())

def _env(workflow, step='worker-resolve'):
    for t in workflow['spec']['templates']:
        if t['name'] == step:
            return {e['name']: e for e in t['container']['env']}
    raise AssertionError(f'no {step} step in the workflow')

def _prompt(workflow, step='worker-resolve'):
    for t in workflow['spec']['templates']:
        if t['name'] == step:
            return t['container']['args'][0]
    raise AssertionError(f'no {step} step in the workflow')

@intent('INT-FC-R130')
def test_the_instantiation_is_derived_from_two_facts_and_never_declared():
    assert derive_instantiation(has_entry_environment=False, has_repository_target=True) is Instantiation.MANAGED
    assert derive_instantiation(has_entry_environment=False, has_repository_target=False) is Instantiation.MANAGED
    assert derive_instantiation(has_entry_environment=True, has_repository_target=True) is Instantiation.HYBRID
    assert derive_instantiation(has_entry_environment=True, has_repository_target=False) is Instantiation.COMPLETE

@intent('INT-FC-R130')
def test_the_service_derives_each_tier_from_the_app_itself():
    assert _svc(FakeSource(HOME_CONTRACT, installs={})).instantiation.execute('org/app') is Instantiation.MANAGED
    assert _svc(FakeSource(HOME_CONTRACT, {'example': ['prod']})).instantiation.execute('org/app') is Instantiation.HYBRID
    assert _svc(FakeSource(ENV_CONTRACT, {'example': ['prod']})).instantiation.execute('org/app') is Instantiation.COMPLETE
    assert make_capabilities(FakeRepos()).instantiation.execute('org/app') is Instantiation.COMPLETE

@intent('INT-FC-R130')
def test_only_a_managed_app_has_a_home():
    """A Hybrid app declares the same repository target, and its work is built and proven HERE
    then promoted there. Reaching for its home during maintenance would send an ordinary
    ticket's fix straight into someone else's review queue - so the TIER, not the target's
    presence, is what decides."""
    assert invoke_helper(_svc(FakeSource(HOME_CONTRACT, installs={})), '_home_target', 'org/app').repo == 'acme/portal'
    assert invoke_helper(_svc(FakeSource(HOME_CONTRACT, {'example': ['prod']})), '_home_target', 'org/app') is None
    assert invoke_helper(_svc(FakeSource(ENV_CONTRACT, installs={})), '_home_target', 'org/app') is None

@intent('INT-FC-R131')
def test_a_managed_act_clones_their_repo_and_keeps_the_ticket_on_ours():
    home = PairHome(repo='acme/portal', branch='main', credential=PairCredential(secret_name='fc-pair-acme-portal-push-key', host_cm='fc-pair-acme-portal-push'))
    wf = compile_maintenance_workflow('org/app-foundry-side', 'resolve', 7, MaintenanceMode.GATED, RunConfig('tok', 'org/app-foundry-side', True), run_id='m1', home=home)
    env = _env(wf)
    assert env['FC_REPO']['value'] == 'org/app-foundry-side'
    assert env['FC_PAIR_REPO']['value'] == 'acme/portal'
    assert env['FC_HOME_BRANCH']['value'] == 'main'
    assert env['FC_PAIR_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-pair-acme-portal-push-key'
    prompt = _prompt(wf)
    assert 'acme/portal' in prompt and 'org/app-foundry-side' in prompt
    assert 'Never merge it' in prompt
    assert 'conformance' in prompt

@intent('INT-FC-R131')
def test_an_ordinary_act_gains_nothing_of_the_home():
    wf = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.GATED, RunConfig('tok', 'org/app', True), run_id='m2')
    env = _env(wf)
    assert env['FC_PAIR_REPO']['value'] == ''
    assert env['FC_HOME_BRANCH']['value'] == ''
    assert 'FC_PAIR_TOKEN' not in env
    assert 'home is' not in _prompt(wf)

@intent('INT-FC-R131')
def test_the_home_directive_is_empty_for_an_app_we_hold():
    assert home_directive(None, 'org/app') == ''

@intent('INT-FC-R132')
def test_one_shot_is_admitted_over_a_managed_app_and_carries_the_home():
    """The merge is the only act a home withholds; the loop is not. A one-shot drive over a
    Managed app compiles the same resolve-then-review run as any other, every step carrying
    the home, and is tracked for the judge like any one-shot drive."""
    svc = _svc(workflows=FakeWorkflows())
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    receipt = svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    assert receipt.mode.value == 'one-shot'
    wf = svc.drive.workflows.submitted[0]
    steps = [s[0]['name'] for s in next((t for t in wf['spec']['templates'] if t['name'] == 'line'))['steps']]
    assert steps == ['resolve', 'review']
    for step in ('worker-resolve', 'worker-review'):
        env = _env(wf, step)
        assert env['FC_PAIR_REPO']['value'] == 'acme/portal'
        assert env['FC_HOME_BRANCH']['value'] == 'main'
    assert any((e['ticket'] == 7 and (not e['acted']) for e in svc.refresh.observations.oneshot.values()))
    receipt = svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    assert receipt.mode.value == 'gated'
    env = _env(svc.drive.workflows.submitted[1])
    assert env['FC_PAIR_REPO']['value'] == 'acme/portal'

@intent('INT-FC-R132')
def test_a_drive_is_refused_when_the_homes_credential_is_not_held():
    svc = _svc(workflows=FakeWorkflows())
    with pytest.raises(ValueError) as exc:
        svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    assert 'acme-portal-push' in str(exc.value)

@intent('INT-FC-R132')
def test_the_merge_press_is_refused_for_a_managed_app():
    """The merge is the other organization's act. Refused by the MODEL rather than left to
    fail on permissions, which would come back the day a grant got broader."""
    acts = FakeActs()
    svc = _svc(acts=acts)
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    from orchestrator.domain.exceptions.conflict import Conflict
    with pytest.raises(Conflict) as exc:
        svc.maintenance_merge.execute('org/app', 14, **command_kwargs('org/app'))
    assert 'the merge is theirs' in str(exc.value).lower() or 'merge' in str(exc.value)
    assert acts.merged == []
    ours = _svc(FakeSource(ENV_CONTRACT, {'example': ['prod']}), acts=acts)
    assert ours.maintenance_merge.execute('org/app', 14, **command_kwargs('org/app')) == PullMergeResult(True)
    assert acts.merged == [('org/app', 14)]

class FakeManagedMaint:
    """OUR tickets, with the marked comment a resolve left on one of them.

    The home's PRs are not here: reaching another organisation is the door's, not the
    maintenance source's (#167), and the split in these fakes is the split in the ports."""

    def __init__(self, comments=None):
        self._comments = comments or {}
        self.listed_our_prs = 0

    def open_issues(self, repo):
        return tuple(semantic_issue(record) for record in ([{'number': 7, 'title': 'Fix the thing', 'user': {'login': 'x'}, 'labels': []}, {'number': 8, 'title': 'Another', 'user': {'login': 'x'}, 'labels': []}]))

    def open_prs(self, repo):
        self.listed_our_prs += 1
        return tuple(semantic_pr(record) for record in ([]))

    def closed_prs(self, repo):
        return tuple(semantic_pr(record) for record in ([]))

    def issue_comments(self, repo, number):
        return tuple(semantic_comment(record) for record in (self._comments.get(number, [])))

    def tags(self, repo):
        return ['v9.9.9']

    def unreleased_subjects(self, repo):
        return ['feat: something']

    def default_branch_checks(self, repo):
        return tuple(semantic_check(record) for record in ([{'conclusion': 'failure'}]))

    def pr_reviews(self, repo, n):
        return tuple(semantic_review(record) for record in ([]))

    def check_runs(self, repo, sha):
        return tuple(semantic_check(record) for record in ([]))

class FakeDoor:
    def repository_revision(self, repo, branch, credential):
        return "home-head"

    """The home's pull requests, readable only on the pair's credential. Records every
    read, so a test can prove the home was asked for exactly the PR the ticket points at
    and nothing else - a Managed ticket never costs the pair a listing."""

    def __init__(self, home_prs=None):
        self._home_prs = home_prs or {}
        self.home_reads: list[tuple] = []

    def pull_request(self, repo, number, credential):
        self.home_reads.append((repo, number, credential))
        return semantic_pr(self._home_prs[(repo, number)]) if (repo, number) in self._home_prs else None

    def open_pull_requests(self, repo, base, credential):
        raise AssertionError('a Managed ticket follows its pointer; it never lists theirs')

    def closed_pull_requests(self, repo, base, credential):
        raise AssertionError('a Managed ticket follows its pointer; it never lists theirs')
POINTER = [{'body': '<!-- foundry:home-pr https://github.com/acme/portal/pull/14 -->\n\nResolved in acme/portal#14.'}]

def _managed_svc(maint, door=None):
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), msource=maint, psource=FakeSource(HOME_CONTRACT, installs={}), door=door if door is not None else FakeDoor())
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    return svc

@intent('INT-FC-R135')
def test_a_managed_ticket_is_followed_to_the_one_home_pr_it_points_at():
    maint = FakeManagedMaint(comments={7: POINTER})
    door = FakeDoor(home_prs={('acme/portal', 14): {'number': 14, 'state': 'open', 'title': 'Fix the thing', 'head': {'ref': 'fix/7-the-thing', 'sha': 'a' * 40}, 'body': 'Resolves org/app#7', 'user': {'login': 'their-bot'}, 'html_url': 'https://github.com/acme/portal/pull/14', 'reviews': [], 'check_runs': []}})
    positions = _managed_svc(maint, door).maintenance_positions.execute('org/app')
    assert door.home_reads == [('acme/portal', 14, 'acme-portal-push')]
    assert maint.listed_our_prs == 0
    assert [p.number for p in positions.prs] == [14]
    assert positions.prs[0].state == 'open'

@intent('INT-FC-R135')
def test_a_pointer_is_the_link_even_when_the_home_branch_follows_their_convention():
    maint = FakeManagedMaint(comments={7: POINTER})
    door = FakeDoor(home_prs={('acme/portal', 14): {'number': 14, 'state': 'open', 'title': 'Tidy the widget', 'head': {'ref': 'feature/widget-tidy', 'sha': 'a' * 40}, 'body': '', 'user': {'login': 'their-bot'}, 'reviews': [], 'check_runs': []}})
    positions = _managed_svc(maint, door).maintenance_positions.execute('org/app')
    assert [p.number for p in positions.prs] == [14]
    from orchestrator.application.maintenance_resolver import pr_resolves_ticket
    pr = positions.prs[0]
    assert pr_resolves_ticket(pr.head, pr.title, '(resolves org/app#7)', 7)
    assert not pr_resolves_ticket(pr.head, pr.title, '(resolves org/app#7)', 8)

@intent('INT-FC-R135')
def test_a_managed_app_has_no_release_train_whatever_the_repo_host_says():
    maint = FakeManagedMaint(comments={})
    positions = _managed_svc(maint).maintenance_positions.execute('org/app')
    assert positions.train.version == ''
    assert positions.train.next_version == ''
    assert positions.train.unreleased_total == 0
    assert positions.prs == ()

@intent('INT-FC-R135')
def test_a_pointer_whose_pr_cannot_be_read_is_not_resolved():
    maint = FakeManagedMaint(comments={7: POINTER})
    door = FakeDoor(home_prs={})
    positions = _managed_svc(maint, door).maintenance_positions.execute('org/app')
    assert positions.prs == ()
    assert door.home_reads == [('acme/portal', 14, 'acme-portal-push')]

@intent('INT-FC-R135')
def test_the_state_offers_one_shot_and_names_the_home():
    svc = _managed_svc(FakeManagedMaint())
    state = observe_repo(svc, 'org/app').maintenance_state.execute('org/app')
    assert state['home'] == {'repo': 'acme/portal', 'branch': 'main', 'credential': 'acme-portal-push'}
    assert {'gated', 'one-shot', 'direct'} <= set(state['action']['modes'])
    ours = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), msource=FakeManagedMaint(), psource=FakeSource(ENV_CONTRACT, {'example': ['prod']}))
    state = observe_repo(ours, 'org/app').maintenance_state.execute('org/app')
    assert state['home'] is None and 'one-shot' in state['action']['modes']

@intent('INT-FC-R136')
def test_a_managed_delivery_keeps_the_scratch_here_and_clones_the_home_beside_it(tmp_path):
    from dataclasses import replace
    from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
    from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
    from orchestrator.domain.model.run_mode import RunMode
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    state = replace(derive_state(str(tmp_path / 'acme')), scratch_ref='delivery/2026-08-21')
    home = PairHome(repo='acme/portal', branch='main', credential=PairCredential(secret_name='fc-pair-acme-portal-push-key', host_cm='fc-pair-acme-portal-push'))
    wf = compile_workflow('org/acme', state, RunConfig('tok', 'org/acme', True, RunMode.INTERACTIVE), run_id='d1', home=home)
    workers = [t for t in wf['spec']['templates'] if t['name'].startswith('worker-')]
    assert workers, 'a fresh line compiles at least one phase'
    for t in workers:
        env = {e['name']: e for e in t['container']['env']}
        assert env['FC_REPO']['value'] == 'org/acme'
        assert env['FC_SCRATCH_REF']['value'] == 'delivery/2026-08-21'
        assert env['FC_PAIR_REPO']['value'] == 'acme/portal'
        assert env['FC_HOME_BRANCH']['value'] == 'main'
        assert env['FC_PAIR_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-pair-acme-portal-push-key'
        prompt = t['container']['args'][0]
        assert '$FC_HOME_DIR' in prompt and '/work/repo/.delivery/' in prompt
        assert 'proven in THEIR CI' in prompt and 'Never merge it yourself' in prompt

@intent('INT-FC-R136')
def test_an_ordinary_delivery_carries_no_home(tmp_path):
    from dataclasses import replace
    from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
    from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
    from orchestrator.domain.model.run_mode import RunMode
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    state = replace(derive_state(str(tmp_path / 'acme')), scratch_ref='delivery/2026-08-21')
    wf = compile_workflow('org/acme', state, RunConfig('tok', 'org/acme', True, RunMode.INTERACTIVE), run_id='d2')
    for t in (t for t in wf['spec']['templates'] if t['name'].startswith('worker-')):
        env = {e['name']: e for e in t['container']['env']}
        assert env['FC_HOME_BRANCH']['value'] == '' and 'FC_PAIR_TOKEN' not in env
        assert 'FC_HOME_DIR' not in t['container']['args'][0]
GREEN = [{'status': 'completed', 'conclusion': 'success'}]

def _review(body, author='fc-review'):
    """A review as the door folds it into the home PR: a different account from the
    resolver that opened the PR, holding write access, posted as the review state section 5
    records its verdict as (INT-FC-R66)."""
    return {'user': {'login': author}, 'body': body, 'submitted_at': 't', 'author_association': 'MEMBER', 'state': _posted_as(body)}

def _home_pr(reviews, checks=GREEN, state='open', merged_at=None):
    return {'number': 14, 'state': state, 'merged_at': merged_at, 'user': {'login': 'fc-git'}, 'head': {'ref': 'fix/7-thing', 'sha': 'a' * 40}, 'title': 'fix(#7): the thing', 'body': 'Closes #7', 'reviews': reviews, 'check_runs': checks}

class _JudgeWorkflows(FakeWorkflows):
    """An executor whose runs have finished: the judge reads them as Succeeded and derives
    its ledger from the rows, one one-shot resolve run per attempt."""

    def __init__(self, attempts):
        super().__init__()
        self._attempts = attempts

    def status(self, handle):
        return 'Succeeded'

    def list_runs(self):
        return run_rows([{'kind': 'maintenance', 'handle': f'live:workflow.argoproj.io/maint-resolve-app-x{i}', 'name': f'maint-resolve-app-x{i}', 'maintenance': 'resolve', 'mode': 'one-shot', 'ticket': '7', 'repo': 'org/app', 'repo_slug': 'app', 'phase': 'Succeeded', 'created': f't{i}'} for i in range(self._attempts, 0, -1)])

def _judge_svc(maint, door, acts, attempts=1):
    from types import SimpleNamespace
    svc = make_capabilities(FakeRepos(), workflows=_JudgeWorkflows(attempts), credentials=FakeCredentials(), config=InMemoryConfigStore(), msource=maint, psource=FakeSource(HOME_CONTRACT, installs={}), door=door, macts=acts)
    svc.set_pair_credential.execute('acme-portal-push', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    svc.refresh.observations.fleet = [SimpleNamespace(name='app', repo='org/app')]
    return svc

@intent('INT-FC-R132')
def test_one_shot_over_a_managed_app_ends_at_the_proven_home_pr_and_never_merges():
    """The loop ran to its end: the home PR carries a recorded PASS on green checks. The
    engine withholds the one act that is theirs, says so in as many words, and read the
    home for exactly the PR the ticket points at - never our PR list, never theirs."""
    maint = FakeManagedMaint(comments={7: POINTER})
    door = FakeDoor({('acme/portal', 14): _home_pr([_review('reads right\nVERDICT: PASS')])})
    acts = FakeActs()
    svc = _judge_svc(maint, door, acts)
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == []
    row = next((e for e in svc.refresh.observations.oneshot.values() if e['ticket'] == 7))
    assert row['acted']
    assert 'acme/portal#14' in row['result'] and 'theirs to merge' in row['result']
    assert door.home_reads == [('acme/portal', 14, 'acme-portal-push')]
    assert maint.listed_our_prs == 0
    assert svc.drive.workflows.submitted == []

@intent('INT-FC-R132')
def test_a_fail_over_a_managed_app_redrives_on_the_findings_carrying_the_home():
    """A recorded FAIL on the home PR is the reviewer's work order, exactly as over an app we
    hold: the resolve is re-driven with the findings threaded in, and the re-driven worker
    carries the home so it revises THEIR PR rather than opening one on ours."""
    maint = FakeManagedMaint(comments={7: POINTER})
    door = FakeDoor({('acme/portal', 14): _home_pr([_review('the error path is untested\nVERDICT: FAIL')])})
    acts = FakeActs()
    svc = _judge_svc(maint, door, acts)
    invoke_helper(svc, '_judge_oneshot_runs')
    assert acts.merged == []
    assert len(svc.drive.workflows.submitted) == 1
    wf = svc.drive.workflows.submitted[0]
    for step in ('worker-resolve', 'worker-review'):
        assert _env(wf, step)['FC_PAIR_REPO']['value'] == 'acme/portal'
    prompt = _prompt(wf)
    assert 'VERDICT: FAIL' in prompt and 'the error path is untested' in prompt
    assert 'Do NOT open a new PR' in prompt
    assert any(('attempt 2/2' in e['result'] for e in svc.refresh.observations.oneshot.values()))
    spent = _judge_svc(maint, door, FakeActs(), attempts=2)
    invoke_helper(spent, '_judge_oneshot_runs')
    assert spent.drive.workflows.submitted == []
    assert any(('degraded' in e['result'] and 'acme/portal#14' in e['result'] for e in spent.refresh.observations.oneshot.values()))

@intent('INT-FC-R132')
def test_a_managed_drive_with_no_recorded_pointer_parks_rather_than_guessing():
    """No pointer on our ticket means the resolve never proved a home PR: the judge parks and
    says so, and it does not go looking through the home's PR list for one."""
    maint = FakeManagedMaint(comments={})
    door = FakeDoor({})
    svc = _judge_svc(maint, door, FakeActs())
    invoke_helper(svc, '_judge_oneshot_runs')
    row = next((e for e in svc.refresh.observations.oneshot.values() if e['ticket'] == 7))
    assert row['acted'] and 'no home PR recorded' in row['result']
    assert door.home_reads == [] and maint.listed_our_prs == 0
