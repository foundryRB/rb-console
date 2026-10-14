"""Typed opaque compilation, adapter rendering and durable delegated submission."""

import json
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest
from capability_support import command_kwargs

from orchestrator.adapters.outbound.archives.operation_receipt_store import (
    OperationReceiptStore,
)
from orchestrator.adapters.outbound.argo.argo_workflow_compiler import (
    ArgoWorkflowCompiler,
)
from orchestrator.adapters.outbound.argo.argo_workflow_runner import ArgoWorkflowRunner
from orchestrator.application.services.operations.admitted_workflow_runner import (
    AdmittedWorkflowRunner,
)
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_retention import RunRetention


def compiled():
    return ArgoWorkflowCompiler().compile_maintenance(
        "org/app",
        "resolve",
        7,
        MaintenanceMode.ONE_SHOT,
        RunConfig("credential", "org/app", True),
        run_id="m-run",
        source_revision="a" * 40,
        retention=RunRetention(2, 3, 14),
    )


def test_compiled_execution_is_an_immutable_value_without_executor_parsing():
    value = CompiledWorkflow("execution", "run", "org/app", "opaque input")
    with pytest.raises(FrozenInstanceError):
        value.executor_payload = "changed"
    assert restore_result(safe_value(value), CompiledWorkflow) == value
    assert not isinstance(value, dict)


def test_compiler_renders_retention_and_stable_coordinates_inside_its_adapter():
    value = compiled()
    assert (value.name, value.run_id, value.repository) == ("m-run", "m-run", "org/app")
    payload = json.loads(value.executor_payload)
    assert payload["metadata"]["name"] == value.name
    assert "generateName" not in payload["metadata"]
    assert (
        payload["metadata"]["annotations"]["foundry-console/source-revision"]
        == "a" * 40
    )
    assert payload["spec"]["podGC"]["deleteDelayDuration"] == "2h"
    assert payload["spec"]["ttlStrategy"] == {
        "secondsAfterSuccess": 3 * 86400,
        "secondsAfterFailure": 14 * 86400,
    }


def test_runner_deserializes_and_adds_only_the_opaque_grant_reference(monkeypatch):
    value = compiled()
    seen = []

    def run(command, **kwargs):
        seen.append(json.loads(kwargs["input"]))
        return SimpleNamespace(
            returncode=0, stdout="workflow.argoproj.io/m-run", stderr=""
        )

    monkeypatch.setenv("FC_DRIVE_LIVE", "1")
    monkeypatch.setattr(
        "orchestrator.adapters.outbound.argo.argo_workflow_runner.subprocess.run", run
    )
    assert (
        ArgoWorkflowRunner().submit(value, delegated_grant_id="opaque-grant")
        == "live:workflow.argoproj.io/m-run"
    )
    assert json.loads(
        seen[0]["metadata"]["annotations"]["foundry-console/delegated-grant"]
    ) == {"grant_id": "opaque-grant"}
    assert (
        "foundry-console/delegated-grant"
        not in json.loads(value.executor_payload)["metadata"]["annotations"]
    )
    for field in ("name", "run_id", "repository"):
        with pytest.raises(ValueError, match="identity"):
            ArgoWorkflowRunner().submit(replace(value, **{field: "other"}))
    assert len(seen) == 1


@pytest.mark.parametrize("lost_response", [False, True])
def test_delegated_dispatch_persists_intent_before_grant_and_never_submits_twice(
    tmp_path, lost_response
):
    archive = OperationReceiptStore(tmp_path)
    admission = OperationAdmission(archive)
    context = command_kwargs("org/app")["context"]
    value = compiled()
    key = admission.key(
        context, "maintenance.drive", "org/app", "reconcile:submit:" + value.name
    )
    calls = []

    class Runner:
        def submit(self, workflow, *, delegated_grant_id=None):
            assert isinstance(workflow, CompiledWorkflow)
            assert archive.get(key).state == "dispatched"
            assert archive.get_grant(delegated_grant_id) is not None
            calls.append(delegated_grant_id)
            if lost_response:
                raise RuntimeError("submission response lost")
            return "live:workflow.argoproj.io/m-run"

    runner = AdmittedWorkflowRunner(Runner(), admission, context, "org/app")
    if lost_response:
        for _ in range(2):
            with pytest.raises(OperationUnknown):
                runner.submit(value)
    else:
        assert runner.submit(value) == runner.submit(value)
    assert len(calls) == 1
    assert value == compiled()
    with pytest.raises(PermissionDenied):
        runner.submit(replace(value, repository="other/app"))
