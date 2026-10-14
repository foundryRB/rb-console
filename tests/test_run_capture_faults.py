from execution_fixtures import run_row, execution_graph
"""Executor capture faults preserve uncaptured workflow evidence for retry."""
import json
import subprocess
from types import SimpleNamespace

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.archives.file_run_log_store import FileRunLogStore
from orchestrator.adapters.outbound.argo.argo_workflow_runner import ArgoWorkflowRunner
from orchestrator.application.services.runs.end_runs import helper_end_runs
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata

MODULE = 'orchestrator.adapters.outbound.argo.argo_workflow_runner'
HANDLE = 'live:workflow.argoproj.io/run'
PODS = {'items': [{'metadata': {'name': 'run-pod'}, 'spec': {'containers': [{'name': 'wait'}, {'name': 'main'}]}}]}

def result(stdout='', returncode=0, stderr=''):
    return SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)

@pytest.mark.parametrize('fault', ['inventory', 'container'])
@intent('INT-FC-R108')
def test_capture_failure_never_marks_archive_or_deletes_workflow(monkeypatch, tmp_path, fault):
    runner = ArgoWorkflowRunner()
    row = run_row({'name': 'run', 'handle': HANDLE, 'phase': 'Succeeded'})
    monkeypatch.setattr(runner, 'list_runs', lambda: [row])
    monkeypatch.setattr(runner, 'metadata_of', lambda handle: WorkflowMetadata('org/app', 'v1', 'uid1', 'delivery', 'delivery/current'))
    monkeypatch.setattr(runner, 'graph', lambda handle: execution_graph({'nodes': []}))
    deleted = []
    monkeypatch.setattr(runner, 'delete', lambda *args, **kwargs: deleted.append((args, kwargs)))
    failed = True
    def kubectl(args, **kwargs):
        assert 0 < kwargs['timeout'] <= 30
        if args[1:3] == ['get', 'pods']:
            if failed and fault == 'inventory':
                return result(returncode=1, stderr='Forbidden')
            return result(json.dumps(PODS))
        if failed and args[args.index('-c') + 1] == 'main':
            return result(returncode=1, stderr='container log unavailable')
        return result('evidence')
    monkeypatch.setattr(MODULE + '.subprocess.run', kubectl)
    archive = FileRunLogStore(str(tmp_path))
    retention = SimpleNamespace(execute=lambda: {'ttl_failure_days': 7})
    with pytest.raises(SourceUnavailable):
        helper_end_runs('org/app', workflows=runner, run_log_store=archive, cap_run_retention=retention)
    assert not archive.has('run')
    assert deleted == []
    failed = False
    helper_end_runs('org/app', workflows=runner, run_log_store=archive, cap_run_retention=retention)
    assert archive.has('run')
    assert 'Forbidden' not in archive.load('run')
    assert '[pod/run-pod/main] evidence' in archive.load('run')
    assert len(deleted) == 1

@pytest.mark.parametrize('listing', ['', '{}', '[]', '{"items":null}', '{"items":[{}]}'])
def test_invalid_inventory_is_unavailable(monkeypatch, listing):
    monkeypatch.setattr(MODULE + '.subprocess.run', lambda *args, **kwargs: result(listing))
    with pytest.raises(SourceUnavailable):
        ArgoWorkflowRunner().logs(HANDLE)

def test_confirmed_empty_inventory_is_empty(monkeypatch):
    monkeypatch.setattr(MODULE + '.subprocess.run', lambda *args, **kwargs: result('{"items":[]}'))
    assert ArgoWorkflowRunner().logs(HANDLE) == ''

def test_all_reads_share_one_capture_deadline(monkeypatch):
    times = iter([0, 1, 11, 31])
    monkeypatch.setattr(MODULE + '.time.monotonic', lambda: next(times))
    timeouts = []
    def kubectl(args, **kwargs):
        timeouts.append(kwargs['timeout'])
        return result(json.dumps(PODS) if args[1] == 'get' else 'evidence')
    monkeypatch.setattr(MODULE + '.subprocess.run', kubectl)
    with pytest.raises(SourceUnavailable, match='deadline'):
        ArgoWorkflowRunner().logs(HANDLE)
    assert timeouts == [29, 19]

@pytest.mark.parametrize('exception', [OSError('missing kubectl'), subprocess.TimeoutExpired('kubectl', 30), UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid')])
def test_subprocess_faults_are_typed_unavailability(monkeypatch, exception):
    def unavailable(*args, **kwargs):
        raise exception
    monkeypatch.setattr(MODULE + '.subprocess.run', unavailable)
    with pytest.raises(SourceUnavailable):
        ArgoWorkflowRunner().logs(HANDLE)
