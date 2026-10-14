from delivery_fixtures import record_inputs
"""Delivery command runtime and configuration admission precedes worker effects."""
from dataclasses import replace
import json
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.archives.operation_receipt_store import OperationReceiptStore
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.application.services.operations.operation_admission import OperationAdmission
from orchestrator.container import build_capabilities
from orchestrator.domain.current_lifecycle import CURRENT_PLAYBOOK_REF
from orchestrator.domain.services.delivery_resolution import derive_from_records
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.run_config import RunConfig
from capability_support import TestRepositoryIncarnations

IMAGE = 'worker:1.0.0'

class Source:
    def __init__(self, image=IMAGE, ref=CURRENT_PLAYBOOK_REF):
        state = derive_from_records('org/app', True, record_inputs({}))
        self.state = replace(state, lifecycle=replace(state.lifecycle, source_ref=ref, worker_image=image), revision='a' * 40, scratch_ref='delivery/current')
        self.config_reads = []
    def state_of(self, repository):
        return self.state
    def read_config(self, repository, *, revision=''):
        self.config_reads.append((repository, revision))
        return {'mode': 'one-shot'}

class Credentials:
    def __init__(self):
        self.writes = []
        self.reads = 0
    def has_delivery(self, slug):
        self.reads += 1
        return False
    def delivery_ref(self, slug):
        return 'delivery-agent'
    def put_delivery(self, slug, credential):
        self.writes.append(slug)
        return self.delivery_ref(slug)

class Workflows:
    def __init__(self):
        self.submitted = []
    def list_runs(self):
        return []
    def submit(self, workflow, *, delegated_grant_id=''):
        self.submitted.append(workflow)
        return 'workflow-run'

class Repositories:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.configs = []
    def write_config(self, workspace, config, *, lifecycle=None):
        self.configs.append((workspace, config, lifecycle))
        self.events.append('pin')


def build(tmp_path, source, installed=IMAGE, repositories=None):
    credentials, workflows = Credentials(), Workflows()
    service = build_capabilities(repositories or Repositories(), source=source, config=InMemoryConfigStore(), credentials=credentials, workflows=workflows, worker_image=installed, incarnations=TestRepositoryIncarnations(), admission=OperationAdmission(OperationReceiptStore(str(tmp_path))))
    context = CommandContext('operator', 'local', 'grant', frozenset({'delivery.drive'}), frozenset({'org/app'}), 'policy', 'org')
    return service, context, credentials, workflows


@intent('INT-FC-R172')
@pytest.mark.parametrize(('installed', 'ref'), [(IMAGE, 'b' * 40), ('worker:latest', CURRENT_PLAYBOOK_REF), ('', CURRENT_PLAYBOOK_REF)])
def test_unsupported_runtime_rejects_before_credentials_or_submission(tmp_path, installed, ref):
    service, context, credentials, workflows = build(tmp_path, Source(IMAGE, ref), installed)
    with pytest.raises(ValueError):
        service.drive.execute('org/app', RunConfig('token', 'org/app', True), 'run', context=context, operation_id='operation')
    assert credentials.writes == [] and credentials.reads == 0
    assert workflows.submitted == []


@intent('INT-FC-R172')
@pytest.mark.parametrize('established', ['', 'worker:latest', 'worker:0.9.0', IMAGE])
@pytest.mark.parametrize('installed', ['worker:2.0.0', 'registry/worker@sha256:' + 'c' * 64])
def test_a_line_launches_on_the_installed_worker_for_its_playbook_revision(tmp_path, established, installed):
    service, context, credentials, workflows = build(tmp_path, Source(established), installed)
    result = service.drive.execute('org/app', RunConfig('token', 'org/app', True), 'run', context=context, operation_id='operation')
    document = json.loads(result.workflow.executor_payload)
    images = {t['container']['image'] for t in document['spec']['templates'] if 'container' in t}
    assert images == {installed}
    assert len(workflows.submitted) == 1


def test_delivery_mode_comes_from_configuration_at_the_observed_commit(tmp_path):
    source = Source()
    service, context, credentials, workflows = build(tmp_path, source)
    result = service.drive.execute('org/app', RunConfig('token', 'org/app', True), 'run', context=context, operation_id='operation')
    assert source.config_reads == [('org/app', 'a' * 40)]
    document = json.loads(result.workflow.executor_payload)
    assert document['metadata']['labels']['foundry-console/mode'] == 'one-shot'
    assert not any(item['name'].startswith('gate-') for item in document['spec']['templates'])
    assert credentials.writes == ['app'] and len(workflows.submitted) == 1


@intent('INT-FC-R172')
def test_a_line_without_a_lifecycle_pin_adopts_the_installed_definition_on_its_first_drive(tmp_path):
    """A line no console pinned (opened by hand, or by an earlier console) is driven on the
    installed definition, and the pin is recorded beside its configuration before the run is
    submitted, so the line names the definition it ran."""
    events = []
    repositories = Repositories(events)
    source = Source(IMAGE, '')
    source.read_config = lambda repository, *, revision='': {'mode': 'one-shot', 'presence': 'attended', 'lifecycle': None}
    service, context, _credentials, workflows = build(tmp_path, source, 'worker:2.0.0', repositories)
    original = workflows.submit
    workflows.submit = lambda workflow, **kwargs: (events.append('submit'), original(workflow, **kwargs))[1]
    result = service.drive.execute('org/app', RunConfig('token', 'org/app', True), 'run', context=context, operation_id='operation')
    [(workspace, config, pinned)] = repositories.configs
    assert workspace == 'org/app' and config == {'mode': 'one-shot'}
    assert (pinned.source_ref, pinned.worker_image) == (CURRENT_PLAYBOOK_REF, 'worker:2.0.0')
    assert events == ['pin', 'submit']
    document = json.loads(result.workflow.executor_payload)
    images = {t['container']['image'] for t in document['spec']['templates'] if 'container' in t}
    assert images == {'worker:2.0.0'}
    env = {e['name']: e['value'] for t in document['spec']['templates'] if 'container' in t for e in t['container'].get('env', []) if 'value' in e}
    assert env['FC_PLAYBOOK_REF'] == CURRENT_PLAYBOOK_REF


@intent('INT-FC-R172')
@pytest.mark.parametrize('installed', ['worker:latest', ''])
def test_an_unpinned_line_is_refused_with_its_reason_when_the_installed_worker_is_unversioned(tmp_path, installed):
    repositories = Repositories()
    service, context, credentials, workflows = build(tmp_path, Source(IMAGE, ''), installed, repositories)
    with pytest.raises(ValueError, match='not versioned or digest-pinned'):
        service.drive.execute('org/app', RunConfig('token', 'org/app', True), 'run', context=context, operation_id='operation')
    assert repositories.configs == [] and credentials.writes == [] and workflows.submitted == []


@intent('INT-FC-R172')
def test_a_refused_runtime_reads_as_its_reason_over_http():
    """The refusal is the line's or the installation's state, never a source outage: the
    door answers it as a readable refusal, not as `source unavailable`."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from orchestrator.adapters.inbound.http.errors import register_errors
    from orchestrator.domain.services.runtime_pin import worker_image_for

    app = FastAPI()
    register_errors(app)

    @app.get('/probe')
    def probe():
        worker_image_for(replace(Source().state.lifecycle, source_ref='b' * 40), IMAGE)

    response = TestClient(app).get('/probe')
    assert response.status_code == 422
    assert response.json()['detail'] == "The line's pinned playbook revision has no compatible installed worker"
