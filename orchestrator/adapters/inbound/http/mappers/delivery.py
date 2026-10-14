from __future__ import annotations

import json
from dataclasses import asdict

from orchestrator.adapters.inbound.http.mappers.config import config_dto
from orchestrator.adapters.inbound.http.mappers.studios import _artifact_dto
from orchestrator.domain.model.delivery.next_action import NextAction
from orchestrator.domain.model.delivery_overview import DeliveryOverview
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.services.delivery_controls import derive_delivery_controls
from orchestrator.domain.services.delivery_phase_presentation import phase_presentation


def state_dto(state: DeliveryState) -> dict:
    return {
        "repo": state.repo,
        "exists": state.exists,
        "status": state.status,
        "phase": state.phase,
        "next_skill": state.next_skill,
        "next_command": state.next_command,
        "blocked_gate": state.blocked_gate,
        "gates": [{"name": g.name, "signed_on": g.signed_on} for g in state.gates],
        "records_present": list(state.records_present),
        "learned_on": state.learned_on,
        "seed": state.seed,
        "demo_of": state.demo_of,
        "revision": state.revision,
        "pending_gate": state.blocked_gate,
        "status_label": {
            "not-a-delivery": "Not a delivery",
            "run-phase": "In delivery",
            "awaiting-gate": "Awaiting gate",
            "delivered": "Delivered",
            "learned": "Learned",
            "degraded": "Needs attention",
            "loading": "Loading",
            "unavailable": "Unavailable",
        }.get(state.status, state.status),
        "phase_cells": [
            {
                "key": p.name,
                "label": p.label,
                "record": p.record,
                "step": "done"
                if p.completion == "journal"
                and state.learned_on
                or any(g.name == p.gate and g.signed for g in state.gates)
                else "current"
                if state.phase == p.name
                else "pending",
            }
            for p in state.lifecycle.phases
        ],
    }


def action_dto(action: NextAction) -> dict:
    dto: dict = {
        "kind": action.kind,
        "gate": action.gate,
        "state": state_dto(action.state),
    }
    if action.launch is not None:
        launch = action.launch
        dto["launch"] = {
            "repo": launch.repo,
            "phase": launch.phase,
            "skill": launch.skill,
            "has_credential": bool(launch.credential_ref),
            "mcp_endpoints": list(launch.mcp_endpoints),
            "prompt": launch.prompt,
        }
    if action.handle is not None:
        dto["handle"] = action.handle
    return dto


def drive_dto(result) -> dict:
    """Serialise a DriveResult: the run id, the executor handle, the derived state, and
    the worker step names the Workflow was compiled with.
    """
    steps = [
        t["name"]
        for t in json.loads(result.workflow.executor_payload)
        .get("spec", {})
        .get("templates", [])
        if t["name"].startswith("worker-")
    ]
    return {
        "run_id": result.run_id,
        "handle": result.handle,
        "state": state_dto(result.state),
        "steps": steps,
    }


def overview_dto(
    overview: DeliveryOverview,
    runs: list[RunInventoryEntry] | None = None,
    graphs: dict[str, ExecutionGraph] | None = None,
) -> dict:
    """The delivery cockpit shape: the derived state plus the configured line, each
    phase carrying its question, its gate/record state, the studio it drives, and that
    studio's artifact status. This is the connective 'view of everything' for one delivery.
    """
    state = overview.state
    active = next(
        (
            run
            for run in (runs or [])
            if run.repository == state.repo and run.kind == "delivery"
        ),
        None,
    )
    controls = derive_delivery_controls(
        state.status,
        active.handle if active else None,
        active.phase if active else None,
        {
            phase.name: phase.record in overview.records_on_disk
            for phase in state.lifecycle.phases
        },
        next(
            (
                phase.name
                for phase in state.lifecycle.phases
                if phase.completion == "journal"
            ),
            None,
        ),
    )
    signed = {g.name: g.signed_on for g in state.gates}
    present = set(overview.records_on_disk) or set(state.records_present)
    order = [p.name for p in state.lifecycle.phases]
    current = order.index(state.phase) if state.phase in order else len(order)
    phases = [
        {
            "name": p.name,
            "question": p.question,
            "skill": p.skill,
            "studio": p.studio or None,
            "gate": p.gate or None,
            "gate_signed_on": signed.get(p.gate) if p.gate else None,
            "record": p.record or None,
            "record_present": bool(p.record) and p.record in present,
            "is_current": state.phase == p.name,
            "needs_review": bool(p.record) and p.record in present and (idx > current),
            "artifact": _artifact_dto(overview.artifacts.get(p.artifact)),
            "renderer": {
                "proposal": "scope",
                "design": "design",
                "handoff": "intent",
                "build": "build",
            }.get(p.artifact, "learn" if p.completion == "journal" else "record"),
        }
        for idx, p in enumerate(state.lifecycle.phases)
    ]
    graph = (graphs or {}).get(active.handle if active else None)
    for phase, definition in zip(phases, state.lifecycle.phases):
        phase.update(
            phase_presentation(
                phase,
                graph,
                state.learned_on if definition.completion == "journal" else None,
            )
        )
    return {
        **state_dto(state),
        "config": config_dto(overview.config),
        "phases": phases,
        "controls": asdict(controls),
    }
