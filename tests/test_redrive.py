from capability_support import with_lifecycle
from execution_fixtures import run_rows
"""The gate review's second outcome: re-drive with the operator's feedback. One act,
durable before live - the journal entry lands before the run is submitted, and a failed
journal write refuses the drive - with the feedback threaded verbatim into the re-driven
worker's prompt as a revision clause, the FIRST compiled worker only. Audit: csd-intent ."""
from capability_support import command_kwargs
import datetime
from dataclasses import replace
import pytest
from pytest_intent import intent
from orchestrator.domain.services.delivery_launch import build_worker_launch
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from capability_support import make_capabilities
from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.domain.model.run_config import RunConfig

class OrderedRepos:
    """Records journal appends into a shared order log, so a test can assert the
    journal write lands BEFORE the executor submit (durable before live)."""

    def __init__(self, order):
        self.order = order
        self.entries: list[tuple[str, str]] = []

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        return target

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def append_journal(self, workspace, entry):
        self.order.append('journal')
        self.entries.append((workspace, entry))

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class OrderedWorkflows:

    def __init__(self, order):
        self.order = order

    def list_runs(self):
        return []

    def submit(self, wf):
        self.order.append('submit')
        return 'handle-1'

class BoomRepos(OrderedRepos):

    def append_journal(self, workspace, entry):
        raise RuntimeError('journal write failed')

class RefSource:
    """state_of over the local scratch with the line's ref attached, the way the remote
    source resolves it, so drive compiles exactly as it does in production (the compiler
    refuses a delivery run without a scratch ref)."""

    def scan(self):
        return []

    def state_of(self, repo):
        return replace(derive_state(repo), scratch_ref='delivery/2026-08-18')

    def read_config(self, repo, *, revision=""):
        return {}

    def present_records(self, repo):
        return []

def _repo(tmp_path):
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    return str(tmp_path / 'acme')
CFG = RunConfig('tok', 'acme', True)

@intent('INT-FC-R70')
def test_redrive_feedback_is_journaled_before_the_run_is_submitted(tmp_path):
    order: list[str] = []
    repos, workflows = (OrderedRepos(order), OrderedWorkflows(order))
    svc = make_capabilities(repos, workflows=workflows, source=RefSource())
    result = svc.drive.execute((_command_repository := _repo(tmp_path)), CFG, 'r1', from_phase='scope', feedback='reprice REQ-3', **command_kwargs(_command_repository))
    assert order == ['journal', 'submit']
    _, entry = repos.entries[0]
    assert entry.startswith('## proposal gate: re-driven ')
    assert datetime.date.today().isoformat() in entry
    assert 'reprice REQ-3' in entry
    blob = str(result.workflow)
    assert 'reprice REQ-3' in blob
    assert 'revision, not a first pass' in blob

@intent('INT-FC-R70')
def test_a_failed_journal_write_refuses_the_drive(tmp_path):
    order: list[str] = []
    svc = make_capabilities(BoomRepos(order), workflows=OrderedWorkflows(order), source=RefSource())
    from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
    with pytest.raises(OperationUnknown):
        svc.drive.execute((_command_repository := _repo(tmp_path)), CFG, 'r2', from_phase='scope', feedback='tighten scope', **command_kwargs(_command_repository))
    assert order == []

@intent('INT-FC-R70')
def test_a_plain_drive_journals_nothing(tmp_path):
    order: list[str] = []
    repos = OrderedRepos(order)
    svc = make_capabilities(repos, workflows=OrderedWorkflows(order), source=RefSource())
    svc.drive.execute((_command_repository := _repo(tmp_path)), CFG, 'r3', **command_kwargs(_command_repository))
    assert repos.entries == []
    assert order == ['submit']

@intent('INT-FC-R70')
def test_feedback_threads_into_the_first_compiled_worker_only(tmp_path):
    state = replace(derive_state(_repo(tmp_path)), scratch_ref='delivery/2026-08-18')
    wf = compile_workflow('acme', state, CFG, run_id='r4', feedback='drop the SSO assumption')
    by_name = {t['name']: t for t in wf['spec']['templates'] if t['name'].startswith('worker-')}
    assert 'drop the SSO assumption' in str(by_name['worker-scope'])
    for downstream in ('worker-design', 'worker-intent-plan', 'worker-build-ship'):
        assert 'drop the SSO assumption' not in str(by_name[downstream])

@intent('INT-FC-R70')
def test_the_revision_clause_appears_only_with_feedback():
    steered = build_worker_launch('/w/acme', 'scope', 'deliver-engagement', CFG, feedback='split REQ-2')
    assert 'split REQ-2' in steered.prompt
    assert 'revision, not a first pass' in steered.prompt
    assert 'journal' in steered.prompt.lower()
    assert '.delivery/reviews/' in steered.prompt
    plain = build_worker_launch('/w/acme', 'scope', 'deliver-engagement', CFG)
    assert 'revision' not in plain.prompt

def test_a_new_drive_stops_the_deliverys_older_live_runs(tmp_path):
    """One delivery, one live run: drive stops the repo's parked or running workflows
    before submitting, so a re-drive never leaves a resumable zombie at a gate."""
    order: list[str] = []

    class Workflows(OrderedWorkflows):

        def __init__(self, order):
            super().__init__(order)
            self.stopped: list[str] = []

        def metadata_of(self, handle):
            from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
            return WorkflowMetadata('foreign' if handle == 'h-other' else str(tmp_path / 'acme').lower(), 'v1', handle, 'delivery', '')

        def list_runs(self):
            return run_rows([{'name': 'delivery-acme-park', 'handle': 'h-park', 'phase': 'Suspended'}, {'name': 'delivery-acme-done', 'handle': 'h-done', 'phase': 'Succeeded'}, {'name': 'delivery-other-x', 'handle': 'h-other', 'phase': 'Running'}, {'name': 'delivery-acme-going', 'handle': 'h-going', 'phase': 'Stopping'}])

        def stop(self, handle, terminate=False, reason='operator', *, expected_version=None):
            self.order.append('stop')
            self.stopped.append((handle, reason))
            return 'Stop'
    wf = Workflows(order)
    svc = make_capabilities(OrderedRepos(order), workflows=wf, source=RefSource())
    svc.drive.execute((_command_repository := _repo(tmp_path)), CFG, run_id='r1', **command_kwargs(_command_repository))
    assert wf.stopped == [('h-park', 'superseded')]
    assert order.index('stop') < order.index('submit')

def test_supersede_catches_a_slug_drifted_run(tmp_path):
    """A delivery once addressed both as 'shattered-catacombs' and (a typo) 'shatteredcatacombs'
    left a 2-day zombie the exact-prefix supersede could not see - the two names never shared a
    prefix. Normalized (separator/case-insensitive) matching stops it on the next drive, while a
    maintenance run and an unrelated delivery are left alone."""
    order: list[str] = []

    class Workflows(OrderedWorkflows):

        def __init__(self, order):
            super().__init__(order)
            self.stopped: list[str] = []

        def metadata_of(self, handle):
            from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
            return WorkflowMetadata("foreign" if handle == "h-other" else str(tmp_path / "shattered-catacombs").lower(), "v1", handle, "maintenance" if handle == "h-maint" else "delivery", "")

        def list_runs(self):
            return run_rows([{'name': 'delivery-shatteredcatacombs-nclpq', 'handle': 'h-zombie', 'phase': 'Running'}, {'name': 'delivery-shattered-catacombs-2nwhz', 'handle': 'h-live', 'phase': 'Suspended'}, {'name': 'delivery-other-app-aaaaa', 'handle': 'h-other', 'phase': 'Running'}, {'name': 'maintenance-shattered-catacombs-bbbbb', 'handle': 'h-maint', 'phase': 'Running'}])

        def stop(self, handle, terminate=False, reason='operator', *, expected_version=None):
            self.order.append('stop')
            self.stopped.append(handle)
            return 'Stop'
    scratch = tmp_path / 'shattered-catacombs' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    wf = Workflows(order)
    svc = make_capabilities(OrderedRepos(order), workflows=wf, source=RefSource())
    svc.drive.execute((_command_repository := str(tmp_path / 'shattered-catacombs')), CFG, run_id='r1', **command_kwargs(_command_repository))
    assert set(wf.stopped) == {'h-zombie', 'h-live'}

@intent('INT-FC-R175')
def test_a_finished_run_the_console_cannot_classify_never_refuses_a_drive(tmp_path):
    """Chaos after the 6.18 cutover: every delivery workflow the previous console had
    created carried no captured coordinates, all of them finished, and the supersede scan
    classified each one before the line's own run - so every drive on every line failed
    with 'The workflow execution kind is unavailable or invalid' for as long as a failed
    workflow is retained (30 days). A finished execution is passed over; the live parked
    run of the line is still superseded."""
    from orchestrator.domain.exceptions.conflict import Conflict
    from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
    order: list[str] = []

    class Workflows(OrderedWorkflows):

        def __init__(self, order, legacy_phase):
            super().__init__(order)
            self.stopped: list[str] = []
            self.asked: list[str] = []
            self._legacy_phase = legacy_phase

        def metadata_of(self, handle):
            from orchestrator.domain.model.workflow_metadata import WorkflowMetadata
            self.asked.append(handle)
            if handle == 'h-legacy':
                raise Conflict('The workflow execution kind is unavailable or invalid.')
            return WorkflowMetadata(str(tmp_path / 'acme').lower(), 'v1', handle, 'delivery', '')

        def list_runs(self):
            return run_rows([{'name': 'delivery-acme-lnwfd', 'handle': 'h-legacy', 'phase': self._legacy_phase}, {'name': 'delivery-acme-park', 'handle': 'h-park', 'phase': 'Suspended'}])

        def stop(self, handle, terminate=False, reason='operator', *, expected_version=None):
            self.order.append('stop')
            self.stopped.append((handle, reason))
            return 'Stop'
    wf = Workflows(order, 'Failed')
    svc = make_capabilities(OrderedRepos(order), workflows=wf, source=RefSource())
    svc.drive.execute((_command_repository := _repo(tmp_path)), CFG, run_id='r1', **command_kwargs(_command_repository))
    assert wf.stopped == [('h-park', 'superseded')] and 'submit' in order
    # A LIVE execution the console cannot place still refuses the drive: the scan would
    # have to stop it, and must not act on what it cannot classify.
    live = Workflows([], 'Running')
    svc = make_capabilities(OrderedRepos([]), workflows=live, source=RefSource())
    with pytest.raises(OperationUnknown):
        svc.drive.execute(_command_repository, CFG, run_id='r2', **command_kwargs(_command_repository))
    assert live.stopped == []
