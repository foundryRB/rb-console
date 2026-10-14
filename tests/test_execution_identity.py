from execution_fixtures import run_rows, execution_graph
"""Execution identity is captured metadata shared by inventory and commands."""
import json

import pytest

from orchestrator.adapters.outbound.argo.argo_workflow_compiler import (
    ArgoWorkflowCompiler,
)
from orchestrator.adapters.outbound.argo.argo_workflow_runner import (
    ArgoWorkflowRunner,
    parse_runs,
)
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.target_kind import TargetKind


@pytest.mark.parametrize("kind", ["delivery", "maintenance", "promotion"])
def test_actual_compiled_inventory_and_command_metadata_share_kind(kind, monkeypatch):
    repo = "owner/app"
    config = RunConfig("credential", repo, True)
    compiler = ArgoWorkflowCompiler()
    if kind == "delivery":
        state = DeliveryState(repo, True, "run-phase", "scope", None, None, None, (), (), scratch_ref="delivery/current")
        workflow = compiler.compile_delivery(repo, state, config, run_id="d-new")
    elif kind == "maintenance":
        workflow = compiler.compile_maintenance(repo, "review", 14, MaintenanceMode.GATED, config, run_id="m-new", source_revision="a" * 40)
    else:
        target = PromotionTarget("production", TargetKind.ENVIRONMENT, "commit", "version", "probe", install="test", environment="production")
        workflow = compiler.compile_promotion(repo, target, "1.0.0", config, run_id="p-new", source_revision="a" * 40)
    payload = json.loads(workflow.executor_payload)
    payload["status"] = {"phase": "Running"}
    row = parse_runs({"items": [payload]})[0]
    assert row.repository == repo and row.kind == kind
    assert row.name == workflow.run_id
    if kind == "maintenance":
        assert row.maintenance_act == "review" and row.ticket == 14
    if kind == "promotion":
        assert row.promotion_target == "production"
    runner = ArgoWorkflowRunner()
    monkeypatch.setattr(runner, "_read", lambda handle: payload)
    assert runner.metadata_of(row.handle).kind == kind


@pytest.mark.parametrize("labels,annotations", [
    ({}, {}),
    ({"foundry-console/maintenance": "resolve", "foundry-console/promotion": "prod"}, {}),
    ({"foundry-console/maintenance": "resolve"}, {"foundry-console/scratch-ref": "delivery/current"}),
    ({"foundry-console/maintenance": []}, {}),
])
def test_ambiguous_or_missing_kind_is_unknown_and_cannot_control_run(labels, annotations, monkeypatch):
    payload = {"metadata": {"name": "maint-looking-name", "labels": {"foundry-console/run": "m-new", **labels}, "annotations": {"foundry-console/repository": "owner/app", **annotations}}, "status": {"phase": "Running"}}
    row = parse_runs({"items": [payload]})[0]
    assert row.kind is None
    runner = ArgoWorkflowRunner()
    monkeypatch.setattr(runner, "_read", lambda handle: payload)
    with pytest.raises(Conflict, match="execution kind"):
        runner.metadata_of(row.handle)


def test_ticket_projection_excludes_same_slug_foreign_repository_and_other_kinds():
    from orchestrator.domain.services.maintenance.ticket_presentation import (
        ticket_presentation,
    )

    state = {"repo": "owner/app", "positions": {"issues": [{"number": 7}], "prs": [], "recent_closed": []}}
    foreign = {"repo": "other/app", "repo_slug": "app", "kind": "maintenance", "maintenance": "resolve", "ticket": "7", "phase": "Succeeded"}
    promotion = {**foreign, "repo": "owner/app", "kind": "promotion"}
    result = ticket_presentation(state, run_rows([foreign, promotion]))
    resolve = next(cell for cell in result["ticket_lines"]["7"] if cell["key"] == "resolve")
    assert resolve["detail"] == "not driven"
    result = ticket_presentation(state, run_rows([{**foreign, "repo": "owner/app"}]))
    resolve = next(cell for cell in result["ticket_lines"]["7"] if cell["key"] == "resolve")
    assert resolve["detail"] == "ran"


@pytest.mark.parametrize("unsafe", ["same-slug-foreign", "unknown-kind"])
def test_delivery_mapper_selects_exact_repository_and_known_delivery_kind(unsafe):
    from orchestrator.adapters.inbound.http.mappers.delivery import overview_dto
    from orchestrator.domain.model.delivery_overview import DeliveryOverview

    compiler = ArgoWorkflowCompiler()
    state = DeliveryState("owner/app", True, "run-phase", "scope", None, None, None, (), (), scratch_ref="delivery/current")
    rows = []
    for repo, run_id, phase in [("other/app" if unsafe == "same-slug-foreign" else state.repo, "d-unsafe", "Running"), (state.repo, "d-owner", "Suspended")]:
        payload = json.loads(compiler.compile_delivery(repo, state, RunConfig("credential", repo, True), run_id=run_id).executor_payload)
        if run_id == "d-unsafe" and unsafe == "unknown-kind":
            payload["metadata"]["annotations"].pop("foundry-console/scratch-ref")
        payload["status"] = {"phase": phase}
        rows.extend(parse_runs({"items": [payload]}))
    graphs = {
        row.handle: execution_graph({"nodes": [{"type": "Pod", "template": "worker-scope", "phase": "Running" if row.run_id == "d-unsafe" else "Failed"}]})
        for row in rows
    }
    result = overview_dto(DeliveryOverview(state, {}), rows, graphs)
    assert result["controls"]["primary_kind"] == "resume"
    scope = next(phase for phase in result["phases"] if phase["name"] == "scope")
    assert scope["tone"] == "failed"
    assert scope["sub_label"] == "failed"

    result = overview_dto(DeliveryOverview(state, {}), rows[:1], graphs)
    assert result["controls"]["primary_kind"] == "drive"
    assert not result["controls"]["run_in_flight"]
    scope = next(phase for phase in result["phases"] if phase["name"] == "scope")
    assert scope["sub_label"] == "current"
