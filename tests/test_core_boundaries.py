from execution_fixtures import run_rows
from delivery_fixtures import record_inputs
"""Behavioral checks for observation and command authority boundaries."""
from types import SimpleNamespace
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.memory.studios_index import StudioStatusIndex
from orchestrator.adapters.outbound.memory.content_cache import MemoryContentCache
from orchestrator.application.services.delivery.release_parked_run import helper_release_parked_run
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata


@intent('INT-FC-R164')
def test_studio_outage_retains_last_successful_observation():
    cache = StudioStatusIndex()
    first = SimpleNamespace(health=lambda: ['healthy'], artifacts_for=lambda slug: {'build': 'artifact'})
    cache.refresh(first, ['app'])
    def outage(*args):
        raise RuntimeError('unavailable')
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
    with pytest.raises(SourceUnavailable):
        cache.refresh(SimpleNamespace(health=outage, artifacts_for=outage), ['app'])
    assert cache.health() == ['healthy']
    assert cache.artifacts('app') == {'build': 'artifact'}


def test_content_cache_is_bounded_and_isolates_mutable_payloads():
    cache = MemoryContentCache(entries=1)
    cache.put(('org/app', 'sha1', 'file'), {'content': 'old'})
    value = cache.get(('org/app', 'sha1', 'file'))
    value['content'] = 'mutated'
    assert cache.get(('org/app', 'sha1', 'file')) == {'content': 'old'}
    cache.put(('org/app', 'sha2', 'file'), {'content': 'new'})
    assert cache.get(('org/app', 'sha1', 'file')) is None
    assert cache.get(('org/app', 'sha2', 'file')) == {'content': 'new'}


class Workflows:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
    def list_runs(self):
        return run_rows([{'handle': key, 'phase': 'Suspended', 'parked_gate': 'proposal'} for key in ('ours', 'foreign', 'other-scratch')])
    def metadata_of(self, handle):
        return WorkflowMetadata('org/foreign' if handle == 'foreign' else 'org/app', 'version7', handle, 'delivery', 'delivery/other' if handle == 'other-scratch' else 'delivery/current')
    def resume(self, handle, *, expected_version):
        self.calls.append((handle, expected_version))
        if self.fail:
            raise RuntimeError('reply lost')
    def stop(self, handle, *, reason, expected_version):
        self.calls.append(('stop', handle, expected_version))


def test_gate_release_uses_repository_scratch_and_resource_version():
    workflows = Workflows()
    helper_release_parked_run('org/app', 'proposal', workflows=workflows, scratch_ref='delivery/current')
    assert workflows.calls == [('ours', 'version7')]


def test_gate_release_does_not_hide_uncertain_mutation():
    with pytest.raises(RuntimeError, match='reply lost'):
        helper_release_parked_run('org/app', 'proposal', workflows=Workflows(fail=True), scratch_ref='delivery/current')


@intent('INT-FC-R165')
def test_workflow_annotations_cannot_mint_scheduler_authority(tmp_path):
    from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
    from orchestrator.application.services.operations.delegated_grants import DelegatedGrants
    from orchestrator.domain.exceptions.permission_denied import PermissionDenied
    service = DelegatedGrants(OperationReceiptStore(str(tmp_path)), 'current-policy')
    with pytest.raises(PermissionDenied):
        service.resolve('attacker-supplied-grant', 'org/app')


@intent('INT-FC-R165')
def test_server_grant_is_exact_repo_scoped_and_policy_revocable(tmp_path):
    from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
    from orchestrator.application.services.operations.delegated_grants import DelegatedGrants
    from orchestrator.domain.model.command_context import CommandContext
    from orchestrator.domain.exceptions.permission_denied import PermissionDenied
    store = OperationReceiptStore(str(tmp_path))
    service = DelegatedGrants(store, 'current-policy')
    context = CommandContext('operator', 'local', 'grant', frozenset({'maintenance.drive'}), frozenset({'org/app'}), 'current-policy', 'org')
    reference = service.issue(context, 'org/app', 'run1', 600)
    admitted = service.resolve(reference['grant_id'], 'org/app')
    assert admitted.allowed_actions == frozenset({'maintenance.drive', 'maintenance.reconcile'})
    with pytest.raises(PermissionDenied):
        service.resolve(reference['grant_id'], 'org/other')
    with pytest.raises(PermissionDenied):
        DelegatedGrants(store, 'revoked-policy').resolve(reference['grant_id'], 'org/app')


@intent('INT-FC-R164')
def test_observation_cannot_overwrite_a_command_published_during_scan():
    from orchestrator.adapters.outbound.memory.index import DeliveryIndex
    from orchestrator.domain.services.delivery_resolution import derive_from_records
    index = DeliveryIndex()
    old = derive_from_records('org/app', True, record_inputs({}))
    fresh = derive_from_records('org/app', False, record_inputs({}))
    index.put(old)
    class Source:
        def scan(self):
            index.put(fresh)
            return [old]
    index.refresh(Source())
    assert index.get('org/app') is fresh


@intent('INT-FC-R164')
def test_bounded_collection_covers_more_than_forty_and_rejects_stale_coverage():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from orchestrator.application.use_cases.projections.refresh_metadata import RefreshMetadata
    observations = SimpleNamespace(metadata={})
    class Collector:
        def execute(self, repo):
            return {'repo': repo}
    collector = Collector()
    refresh = RefreshMetadata(observations=observations, maintenance=collector, promotion=collector, options=collector, config=collector, batch_size=16)
    repos = [f'org/app{i}' for i in range(60)]
    observations.fleet = [SimpleNamespace(repo=repo) for repo in repos]
    for _ in range(4):
        report = refresh.execute()
    assert report['complete'] is True
    assert report['observed'] == report['total'] == 60
    observations.metadata[repos[-1]]['freshness']['observed_at'] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    report = refresh.execute()
    assert report['complete'] is False
    assert report['observed'] == 60


@intent('INT-FC-R165')
def test_expired_server_grant_cannot_authorize_scheduler(tmp_path):
    from datetime import UTC, datetime, timedelta
    from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
    from orchestrator.application.services.operations.delegated_grants import DelegatedGrants
    from orchestrator.domain.exceptions.permission_denied import PermissionDenied
    store = OperationReceiptStore(str(tmp_path))
    store.save_grant('expired', {'principal_id': 'operator', 'initiator_kind': 'scheduler', 'grant_id': 'expired', 'allowed_actions': ['maintenance.reconcile'], 'repositories': ['org/app'], 'authorization_revision': 'current-policy', 'installation_id': 'org', 'expires_at': (datetime.now(UTC) - timedelta(seconds=1)).isoformat()})
    with pytest.raises(PermissionDenied):
        DelegatedGrants(store, 'current-policy').resolve('expired', 'org/app')


@intent('INT-FC-R164', 'INT-FC-R01')
def test_a_repository_absent_from_a_completed_scan_is_not_a_delivery():
    from orchestrator.adapters.outbound.memory.index import DeliveryIndex
    from orchestrator.application.use_cases.projections.status import Status
    from orchestrator.domain.delivery import NOT_A_DELIVERY
    index = DeliveryIndex()
    status = Status(index=index)
    assert status.execute('org/app').status == 'loading'
    class Source:
        def scan(self):
            return []
    index.refresh(Source())
    state = status.execute('org/app')
    assert (state.exists, state.status, state.next_skill) == (False, NOT_A_DELIVERY, 'deliver-engagement')
