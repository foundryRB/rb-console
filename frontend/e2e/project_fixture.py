"""Project browser fixtures through the backend's pure control and lifecycle rules."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.adapters.inbound.http.mappers.delivery import overview_dto
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from tests.execution_fixtures import run_rows, execution_graph
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.gate_state import GateState
from orchestrator.domain.services.maintenance.ticket_presentation import ticket_presentation
from orchestrator.domain.model.delivery_overview import DeliveryOverview


def project(data: dict, runs: list[dict], graphs: dict) -> dict:
    if "phases" in data and "status" in data and "repo" in data:
        phases = data["phases"]
        gates = tuple(GateState(p["gate"], p.get("gate_signed_on")) for p in phases if p.get("gate"))
        state = DeliveryState(
            repo=data["repo"], exists=data.get("exists", True), status=data["status"],
            phase=data.get("phase"), next_skill=data.get("next_skill"),
            next_command=data.get("next_command"), blocked_gate=data.get("blocked_gate"),
            gates=gates, records_present=tuple(data.get("records_present", [])),
            learned_on=data.get("learned_on"), lifecycle=CURRENT_LIFECYCLE,
        )
        observed_runs = run_rows(runs)
        overview = DeliveryOverview(state, {}, config=data.get("config", {}), records_on_disk=tuple(data.get("records_present", [])))
        canonical = overview_dto(overview, observed_runs, {handle: execution_graph(graph) for handle, graph in graphs.items()})
        indexed = {phase["name"]: phase for phase in canonical["phases"]}
        presentation = ("renderer", "tone", "sub_label")
        return {
            **data,
            "status_label": canonical["status_label"],
            "pending_gate": canonical["pending_gate"],
            "phase_cells": canonical["phase_cells"],
            "controls": canonical["controls"],
            "phases": [{**phase, **{key: indexed.get(phase["name"], {}).get(key) for key in presentation}} for phase in phases],
        }
    if "positions" in data and "action" in data:
        return ticket_presentation(data, run_rows(runs))
    return data


payload = json.load(sys.stdin)
print(json.dumps(project(payload["data"], payload.get("runs", []), payload.get("graphs", {}))))
