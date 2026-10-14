from capability_support import with_lifecycle
from execution_fixtures import run_rows
from orchestrator.domain.model.platform_app import PlatformApp
from orchestrator.domain.model.repository_inventory_entry import RepositoryInventoryEntry
from delivery_fixtures import record_inputs
"""The Fleet view joins every org repo with the delivery index and platform-studio apps,
so a delivery, a live app, and a plain repo are all distinguishable. Audit: csd-intent ."""
from pytest_intent import intent
from orchestrator.adapters.inbound.http.mappers.fleet import fleet_dto
from orchestrator.adapters.outbound.memory.index import DeliveryIndex
from orchestrator.domain.services.delivery_resolution import derive_from_records
from capability_support import make_capabilities
from orchestrator.adapters.outbound.memory.studios_index import StudioStatusIndex

class FakeRepos:

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        return target

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class FakeSource:

    def scan(self):
        return [derive_from_records('example-org/acme', True, record_inputs({'proposal.md': 'proposal accepted 2026-07-09'}))]

    def state_of(self, repo):
        return derive_from_records(repo, False, record_inputs({}))

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='example-org/acme', name='acme', updated_at='t1', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/shipped', name='shipped', updated_at='t2', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/plain', name='plain', updated_at='t3', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/ci', name='ci', updated_at='t4', topics=('foundry-hidden',), repository_id='')]

class FakeGateway:
    def estimatekit_slugs(self):
        return []

    def protopane_slugs(self):
        return []

    def playbook_repo(self):
        return ""


    def health(self):
        return []

    def artifacts_for(self, slug):
        return {}

    def platform_apps(self):
        return [PlatformApp(name='shipped', repository='shipped', onboarded=True, status='running', hostname='', revision='', role='output'), PlatformApp(name='plain', repository='plain', onboarded=False, status='unknown', hostname='', revision='', role='parts')]

class FakeWorkflows:
    """The executor, stubbed: list_runs is the only surface the fleet activity axis reads.
    ``raises`` models an unreachable executor (off-cluster), so the fleet reads 'unknown'."""

    def __init__(self, rows=None, raises=False):
        self._rows = rows or []
        self._raises = raises

    def list_runs(self):
        if self._raises:
            from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
            raise SourceUnavailable('executor unreachable')
        return run_rows(self._rows)

@intent('INT-FC-R38')
def test_fleet_joins_repos_deliveries_and_apps():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex())
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['acme']['is_delivery'] is True and by['acme']['delivery_status']
    assert by['shipped']['onboarded'] is True and by['shipped']['live'] == 'running'
    assert by['plain']['is_delivery'] is False and by['plain']['onboarded'] is False
    assert 'ci' not in by

class MixedCaseSource:
    """An org repo whose GitHub name preserves its casing ('SolveOS'), while the platform
    registry addresses it by its lowercased slug ('solveos'). The real-world drift that hid
    SolveOS from its own live app on the board."""

    def scan(self):
        return []

    def state_of(self, repo):
        return derive_from_records(repo, False, record_inputs({}))

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='example-org/SolveOS', name='SolveOS', updated_at='t1', topics=(), repository_id='')]

class LowerCaseGateway:
    def estimatekit_slugs(self):
        return []

    def protopane_slugs(self):
        return []

    def playbook_repo(self):
        return ""


    def health(self):
        return []

    def artifacts_for(self, slug):
        return {}

    def platform_apps(self):
        return [PlatformApp(name='solveos', repository='solveos', onboarded=True, status='running', hostname='', revision='', role=None)]

    def estimatekit_slugs(self):
        return {'solveos'}

    def protopane_slugs(self):
        return {'solveos'}

@intent('INT-FC-R38')
def test_fleet_matches_app_despite_repo_name_case_drift():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=MixedCaseSource(), studios=LowerCaseGateway(), studio_index=StudioStatusIndex())
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['SolveOS']['onboarded'] is True
    assert by['SolveOS']['live'] == 'running'
    assert by['SolveOS']['estimatekit'] is True
    assert by['SolveOS']['protopane'] is True

class DivergentSource:
    """An org whose repositories are named for the organisation, not the apps they hold."""

    def scan(self):
        return []

    def state_of(self, repo):
        return derive_from_records(repo, False, record_inputs({}))

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='Fleet-Org/fleet-console', name='fleet-console', updated_at='t1', topics=(), repository_id='')]

class DivergentGateway:
    def estimatekit_slugs(self):
        return []

    def protopane_slugs(self):
        return []

    def playbook_repo(self):
        return ""

    """platform-studio for that install: the app is `foundry-console`, and it declares the
    repository it ships from - a different string."""

    def health(self):
        return []

    def artifacts_for(self, slug):
        return {}

    def platform_apps(self):
        return [PlatformApp(name='foundry-console', repository='fleet-console', onboarded=True, status='running', hostname='foundry-console.example.dev', revision='', role='parts')]

@intent('INT-FC-R38')
def test_fleet_joins_an_app_whose_repository_is_named_differently():
    """The join's other side is the ORG's repo listing, so it must key on the repository.

    Keying on the manifest name matched nothing on an install whose repositories carry an
    organisation prefix while its apps keep their own names: every part then read as a bare
    repo - no role, no live status, never onboarded - and the board's whole platform-vs-
    tenant grouping collapsed. The row must also CARRY the app's identity, or every
    consumer downstream (pause/resume, the ArgoCD link, the docs and live URLs) re-derives
    it from the repository's name and is wrong in the same way.
    """
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=DivergentSource(), studios=DivergentGateway(), studio_index=StudioStatusIndex())
    svc.refresh.execute()
    row = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}['fleet-console']
    assert row['onboarded'] is True
    assert row['live'] == 'running'
    assert row['role'] == 'parts'
    assert row['app_name'] == 'foundry-console'
    assert row['host'] == 'foundry-console.example.dev'

@intent('INT-FC-R81')
def test_fleet_joins_live_worker_activity():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex(), workflows=FakeWorkflows([{'name': 'd-parked', 'repo': 'example-org/acme', 'kind': 'delivery', 'phase': 'Suspended', 'handle': 'h0'}, {'name': 'd-active', 'repo': 'example-org/acme', 'kind': 'delivery', 'phase': 'Running', 'handle': 'h1'}, {'name': 'm-active', 'repo': 'example-org/acme', 'kind': 'maintenance', 'phase': 'Running', 'handle': 'h2'}]))
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['acme']['activity'] == 'running'
    assert by['shipped']['activity'] is None

@intent('INT-FC-R81')
def test_fleet_activity_suspended_when_parked_on_a_gate():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex(), workflows=FakeWorkflows([{'name': 'd-active', 'repo': 'example-org/acme', 'kind': 'delivery', 'phase': 'Suspended', 'handle': 'h1'}]))
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['acme']['activity'] == 'suspended'

@intent('INT-FC-R81')
def test_fleet_activity_idle_when_executor_has_no_run():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex(), workflows=FakeWorkflows([]))
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['acme']['activity'] == 'idle'

@intent('INT-FC-R81')
def test_fleet_activity_unknown_without_or_unreachable_executor():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex())
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['acme']['is_delivery'] is True and by['acme']['activity'] is None
    svc2 = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex(), workflows=FakeWorkflows(raises=True))
    svc2.refresh.execute()
    by2 = {p['name']: p for p in fleet_dto(svc2.fleet.execute())['projects']}
    assert by2['acme']['activity'] is None

@intent('INT-FC-R101')
def test_fleet_carries_manifest_role():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex())
    svc.refresh.execute()
    by = {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}
    assert by['shipped']['role'] == 'output'
    assert by['plain']['role'] == 'parts'
    assert by['acme']['role'] is None

@intent('INT-FC-R47')
def test_hidden_repos_are_excluded_unless_requested():
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex())
    svc.refresh.execute()
    assert 'ci' not in {p['name'] for p in fleet_dto(svc.fleet.execute())['projects']}
    shown = {p['name']: p for p in fleet_dto(svc.fleet.execute(include_hidden=True))['projects']}
    assert 'ci' in shown and shown['ci']['hidden'] is True

@intent('INT-FC-R107')
def test_forced_refresh_reads_the_inbox_and_every_repository_off_their_cadence(monkeypatch):
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), msource=object())
    batches = iter([[{'repo': 'a'}], [{'repo': 'b'}], [{'repo': 'c'}]])
    monkeypatch.setattr('orchestrator.application.use_cases.projections.refresh.helper_compute_inbox', lambda **kwargs: next(batches))
    collector = svc.refresh.cap_refresh_metadata
    sweeps = []
    monkeypatch.setattr(collector, 'execute', lambda *, sweep=False: sweeps.append(sweep) or {'complete': True, 'observed': 0, 'total': 0})
    svc.refresh.execute()
    assert svc.maintenance_inbox.execute()['items'] == [{'repo': 'a'}]
    svc.refresh.execute()
    assert svc.maintenance_inbox.execute()['items'] == [{'repo': 'a'}]
    svc.refresh.execute(force=True)
    assert svc.maintenance_inbox.execute()['items'] == [{'repo': 'b'}]
    assert sweeps == [False, False, True]

class CoreSource:
    """The two repos the Foundry is built OUT OF sit in the org list like any other: the
    platform repo (the substrate that renders every teams/ folder) and the playbook (the
    corpus every phase pulls from). Neither is or can be an onboarded app."""

    def scan(self):
        return []

    def state_of(self, repo):
        return derive_from_records(repo, False, record_inputs({}))

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='example-org/foundry-platform', name='foundry-platform', updated_at='t1', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/playbook', name='playbook', updated_at='t2', topics=(), repository_id=''), RepositoryInventoryEntry(repository='example-org/shipped', name='shipped', updated_at='t3', topics=(), repository_id='')]

class CoreGateway:
    def estimatekit_slugs(self):
        return []

    def protopane_slugs(self):
        return []

    """playbook-studio answering with the upstream of the clone it owns. ``repo`` empty
    models every unavailable case at once - studio down, refusal, or a composition
    managing no clone, where get_sync_status is not even a registered tool."""

    def __init__(self, playbook='example-org/playbook'):
        self._playbook = playbook

    def health(self):
        return []

    def artifacts_for(self, slug):
        return {}

    def platform_apps(self):
        return [PlatformApp(name='shipped', repository='shipped', onboarded=True, status='running', hostname='', revision='', role='output')]

    def playbook_repo(self):
        return self._playbook

def _core_fleet(gateway):
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=CoreSource(), studios=gateway, studio_index=StudioStatusIndex())
    svc.refresh.execute()
    return {p['name']: p for p in fleet_dto(svc.fleet.execute())['projects']}

@intent('INT-FC-R147')
def test_platform_and_playbook_carry_the_core_role():
    by = _core_fleet(CoreGateway())
    assert by['foundry-platform']['role'] == 'core'
    assert by['playbook']['role'] == 'core'
    assert by['shipped']['role'] == 'output'

@intent('INT-FC-R147')
def test_unknown_playbook_repo_leaves_the_row_unmarked():
    by = _core_fleet(CoreGateway(playbook=''))
    assert by['playbook']['role'] is None
    assert by['foundry-platform']['role'] == 'core'

@intent('INT-FC-R147')
def test_core_outranks_a_manifest_role():

    class Claiming(CoreGateway):

        def platform_apps(self):
            return [PlatformApp(name='playbook', repository='playbook', onboarded=True, status='running', hostname='', revision='', role='output')]
    assert _core_fleet(Claiming())['playbook']['role'] == 'core'


def test_fleet_activity_uses_compiled_full_repository_identity():
    import json

    from orchestrator.adapters.outbound.argo.argo_workflow_compiler import ArgoWorkflowCompiler
    from orchestrator.adapters.outbound.argo.argo_workflow_runner import parse_runs
    from orchestrator.domain.model.delivery_state import DeliveryState
    from orchestrator.domain.model.run_config import RunConfig

    rows = []
    for repo, run_id, phase, known in [("other-org/acme", "d-foreign", "Running", True), ("example-org/acme", "d-unknown", "Running", False), ("example-org/acme", "d-owned", "Suspended", True)]:
        state = DeliveryState(repo, True, "run-phase", "scope", None, None, None, (), (), scratch_ref="delivery/current")
        payload = json.loads(ArgoWorkflowCompiler().compile_delivery(repo, state, RunConfig("credential", repo, True), run_id=run_id).executor_payload)
        if not known:
            payload["metadata"]["annotations"].pop("foundry-console/scratch-ref")
        payload["status"] = {"phase": phase}
        rows.extend(parse_runs({"items": [payload]}))
    svc = make_capabilities(FakeRepos(), index=DeliveryIndex(), source=FakeSource(), studios=FakeGateway(), studio_index=StudioStatusIndex(), workflows=FakeWorkflows(rows))
    svc.refresh.execute()
    by = {p["name"]: p for p in fleet_dto(svc.fleet.execute())["projects"]}
    assert by["acme"]["activity"] == "suspended"
