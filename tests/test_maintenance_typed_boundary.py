"""Host wire evidence is normalized before entering maintenance core contracts."""
from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

import pytest
from pytest_intent import intent
from test_launch_preflight import setup

from orchestrator.adapters.inbound.http.mappers.maintenance import (
    maintenance_drive_response,
)
from orchestrator.adapters.outbound.github.github_maintenance_source import (
    GitHubMaintenanceSource,
)
from orchestrator.application.ports.inbound.maintenance.maintenance_drive import (
    MaintenanceDrivePort,
)
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.use_cases.maintenance.maintenance_drive import (
    MaintenanceDrive,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.maintenance_drive_result import MaintenanceDriveResult
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.prepared_maintenance_command import (
    PreparedMaintenanceCommand,
)


class Transport:
    def __init__(self, payload):
        self.payload = payload
    def json(self, *args, **kwargs):
        return self.payload

@intent('INT-FC-R163')
@pytest.mark.parametrize('port', [MaintenanceSource, Door])
def test_host_ports_expose_semantic_records(port):
    def assert_typed(value):
        assert value not in (dict, Any, object)
        assert get_origin(value) is not dict
        for item in get_args(value):
            assert_typed(item)
        if isinstance(value, type) and is_dataclass(value):
            assert value.__dataclass_params__.frozen
            for hint in get_type_hints(value).values():
                assert_typed(hint)
    for name, method in vars(port).items():
        if name.startswith('_') or not callable(method):
            continue
        assert_typed(get_type_hints(method)['return'])
    assert get_type_hints(MaintenanceDrivePort.execute)['return'] is MaintenanceDriveResult
    assert get_type_hints(MaintenanceDrive._prepare)['return'] is PreparedMaintenanceCommand

@intent('INT-FC-R163')
def test_github_adapter_flattens_host_evidence():
    raw = {'number': 7, 'user': {'login': 'author'}, 'head': {'ref': 'fix/7-test', 'sha': 'a'*40}, 'title': 'fix(#7)', 'body': 'Closes #7', 'html_url': 'https://github.com/org/app/pull/7'}
    source = GitHubMaintenanceSource('org', lambda: 'token', transport=Transport(raw))
    pr = source.pr('app', 7)
    assert isinstance(pr, MaintenancePullRequest)
    assert (pr.author, pr.head_branch, pr.head_sha, pr.url) == ('author', 'fix/7-test', 'a'*40, raw['html_url'])
    assert not hasattr(pr, 'get')
    with pytest.raises(FrozenInstanceError):
        pr.head_sha = 'other'
    source._transport.payload = {'number': 7, 'labels': [{'name': 'bug'}], 'type': {'name': 'Bug'}, 'pull_request': {}}
    issue = source.issue('app', 7)
    assert isinstance(issue, MaintenanceIssue)
    assert issue.labels == ('bug',) and issue.issue_type == 'Bug' and issue.is_pull_request

@pytest.mark.parametrize('payload', [[], {'user': []}, {'number': 'seven'}, {'labels': 'bug'}, {'labels': [1]}])
def test_malformed_issue_evidence_is_unavailable(payload):
    source = GitHubMaintenanceSource('org', lambda: 'token', transport=Transport(payload))
    with pytest.raises(SourceUnavailable):
        source.issue('app', 7)

@intent('INT-FC-R163')
def test_command_result_survives_receipt_replay_as_typed_value():
    call, context, log, _receipts = setup('maintenance')
    first = call(context)
    replay = call(context)
    assert isinstance(first, MaintenanceDriveResult) and isinstance(replay, MaintenanceDriveResult)
    assert first == replay
    assert maintenance_drive_response(first) == {'run_id': first.run_id, 'handle': first.handle, 'act': 'resolve', 'mode': 'gated'}
    assert log.count('submit') == 1
    assert PreparedMaintenanceCommand.__dataclass_params__.frozen
    assert all(hint not in (dict, Any, object) for hint in get_type_hints(PreparedMaintenanceCommand).values())


def test_preflight_captures_a_named_immutable_plan_before_effects():
    from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
    from orchestrator.domain.model.maintenance_command_evidence import (
        MaintenanceCommandEvidence,
    )
    from orchestrator.domain.model.run_config import RunConfig
    call, context, log, receipts = setup('maintenance')
    service = next(cell.cell_contents for cell in call.__closure__ if isinstance(cell.cell_contents, MaintenanceDrive))
    prepared = service._prepare('org/app', 'resolve', 7, 'gated', RunConfig('secret', 'org/app', True), context=context, operation_id='op')
    assert isinstance(prepared, PreparedMaintenanceCommand)
    assert isinstance(prepared.workflow, CompiledWorkflow)
    assert isinstance(prepared.evidence, MaintenanceCommandEvidence)
    assert prepared.evidence.source_revision == 'sha'
    assert prepared.evidence.repository_id == '123'
    assert 'credential-write' not in log and 'submit' not in log and receipts.rows == {}
    with pytest.raises(FrozenInstanceError):
        prepared.run_id = 'other'
