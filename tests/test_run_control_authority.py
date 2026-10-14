"""Run commands honor live ownership, source gates, CAS and retained receipts."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from orchestrator.adapters.outbound.archives.operation_receipt_store import (
    OperationReceiptStore,
)
from orchestrator.adapters.outbound.argo.argo_workflow_runner import ArgoWorkflowRunner, parse_runs
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.use_cases.runs.resume_run import ResumeRun
from orchestrator.application.use_cases.runs.stop_run import StopRun
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata

HANDLE = "live:workflow.argoproj.io/delivery-app-abc"


def caller():
    return CommandContext(
        "operator",
        "operator",
        "grant",
        frozenset({"runs.stop", "runs.resume"}),
        frozenset({"org/app"}),
        "revision",
        "org",
    )


class Runner:
    metadata = WorkflowMetadata("org/app", "17", "run-uid", "maintenance")

    def __init__(self):
        self.effects = []
        self.reads = 0

    def metadata_of(self, handle):
        self.reads += 1
        return self.metadata

    def stop(
        self, handle, terminate=False, reason="operator", *, expected_version=None
    ):
        self.effects.append(("stop", expected_version))
        return "Stop"

    def resume(self, handle, *, expected_version=None):
        self.effects.append(("resume", expected_version))
        return "resumed:1"


def test_scope_and_revision_rejected_before_effect_and_failed_admission_can_retry(
    tmp_path,
):
    runner = Runner()
    command = StopRun(
        workflows=runner, admission=OperationAdmission(OperationReceiptStore(tmp_path))
    )
    args = {"context": caller(), "operation_id": "stop-1", "expected_revision": "17"}
    runner.metadata = replace(runner.metadata, repository="org/other")
    with pytest.raises(PermissionDenied):
        command.execute(HANDLE, **args)
    runner.metadata = replace(
        runner.metadata, repository="org/app", resource_version="18"
    )
    with pytest.raises(Conflict):
        command.execute(HANDLE, **args)
    assert runner.effects == []
    runner.metadata = replace(runner.metadata, resource_version="17")
    assert command.execute(HANDLE, **args)["shutdown"] == "Stop"
    assert runner.effects == [("stop", "17")]


def test_completed_receipt_survives_executor_gc_and_rechecks_current_scope(tmp_path):
    runner = Runner()
    admission = OperationAdmission(OperationReceiptStore(tmp_path))
    StopRun(workflows=runner, admission=admission).execute(
        HANDLE, context=caller(), operation_id="id"
    )
    restarted = StopRun(
        workflows=None, admission=OperationAdmission(OperationReceiptStore(tmp_path))
    )
    assert (
        restarted.execute(HANDLE, context=caller(), operation_id="id")["shutdown"]
        == "Stop"
    )
    with pytest.raises(PermissionDenied):
        restarted.execute(
            HANDLE,
            context=replace(caller(), repositories=frozenset({"org/other"})),
            operation_id="id",
        )
    assert runner.effects == [("stop", "17")]


def test_lost_executor_reply_never_replays(tmp_path):
    class LostReply(Runner):
        def stop(self, *args, **kwargs):
            super().stop(*args, **kwargs)
            raise ConnectionError("accepted then disconnected")

    runner = LostReply()
    for _ in range(2):
        command = StopRun(
            workflows=runner,
            admission=OperationAdmission(OperationReceiptStore(tmp_path)),
        )
        with pytest.raises(OperationUnknown):
            command.execute(HANDLE, context=caller(), operation_id="id")
    assert len(runner.effects) == 1


@pytest.mark.parametrize("condition", ["unsigned", "wrong_line", "unavailable"])
def test_resume_requires_fresh_gate_and_line_proof(tmp_path, condition):
    runner = Runner()
    runner.metadata = replace(
        runner.metadata, kind="delivery", scratch_ref="delivery/one"
    )

    class Source:
        def state_of(self, repo):
            assert repo == "org/app"
            if condition == "unavailable":
                raise SourceUnavailable("offline")
            return SimpleNamespace(
                exists=True,
                scratch_ref="delivery/other"
                if condition == "wrong_line"
                else "delivery/one",
                status="awaiting-gate",
                blocked_gate="proposal",
            )

    command = ResumeRun(
        source=Source(),
        workflows=runner,
        admission=OperationAdmission(OperationReceiptStore(tmp_path)),
    )
    with pytest.raises(SourceUnavailable if condition == "unavailable" else Conflict):
        command.execute(HANDLE, context=caller(), operation_id="resume")
    assert runner.effects == []


@pytest.mark.parametrize("action", ["stop", "resume"])
def test_kubernetes_mutation_carries_resource_version_precondition(monkeypatch, action):
    workflow = {
        "metadata": {"resourceVersion": "17"},
        "status": {"nodes": {"gate": {"type": "Suspend", "phase": "Running"}}},
    }
    patches = []

    def run(args, **kwargs):
        if args[1] == "get":
            return SimpleNamespace(returncode=0, stdout=json.dumps(workflow), stderr="")
        patches.append(json.loads(args[args.index("-p") + 1]))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(
        "orchestrator.adapters.outbound.argo.argo_workflow_runner.subprocess.run", run
    )
    method = getattr(ArgoWorkflowRunner(), action)
    with pytest.raises(Conflict):
        method(HANDLE, expected_version="16")
    assert not patches
    method(HANDLE, expected_version="17")
    if action == "stop":
        assert patches[0]["metadata"]["resourceVersion"] == "17"
    else:
        assert patches[0][0] == {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": "17",
        }


def test_run_inventory_preserves_delegated_authority_metadata():
    row = parse_runs(
        {
            "items": [
                {
                    "metadata": {
                        "name": "run",
                        "resourceVersion": "17",
                        "annotations": {
                            "foundry-console/repository": "org/app",
                            "foundry-console/delegated-grant": '{"grant_id":"run-1"}',
                        },
                    }
                }
            ]
        }
    )[0]
    assert row.repository == "org/app"
    assert row.resource_version == "17"
    assert row.grant_id == "run-1"


def test_workflow_deletion_binds_archived_version_and_uid(monkeypatch):
    sent = []
    def run(args, **kwargs):
        sent.append((args, json.loads(kwargs["input"])))
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")
    monkeypatch.setattr("orchestrator.adapters.outbound.argo.argo_workflow_runner.subprocess.run", run)
    runner = ArgoWorkflowRunner()
    with pytest.raises(SourceUnavailable):
        runner.delete(HANDLE, expected_version="17", expected_uid="")
    assert not sent
    assert runner.delete(HANDLE, expected_version="17", expected_uid="run-uid") == "deleted"
    assert sent[0][0][1:3] == ["delete", "--raw"]
    assert sent[0][1]["preconditions"] == {"uid": "run-uid", "resourceVersion": "17"}


@pytest.mark.parametrize("response", ["", "{}", "invalid-json"])
def test_unreadable_run_inventory_is_not_an_empty_observation(monkeypatch, response):
    monkeypatch.setenv("FC_DRIVE_LIVE", "1")
    monkeypatch.setattr("orchestrator.adapters.outbound.argo.argo_workflow_runner.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=response, stderr=""))
    with pytest.raises(SourceUnavailable):
        ArgoWorkflowRunner().list_runs()
