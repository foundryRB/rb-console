"""Project the attention queue from already observed repository metadata."""

from __future__ import annotations

from dataclasses import asdict

from orchestrator.application.fleet_inbox import derive_inbox
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.maintenance_positions import MaintenancePositions


def helper_compute_inbox(*, observations: ObservationStore) -> list[dict]:
    positions = []
    promotion = {}
    running = {}
    hidden = {row.repo for row in observations.fleet if row.hidden}
    for row in observations.fleet:
        snapshot = observations.metadata.get(row.repo, {})
        current = snapshot.get("maintenance_state") or {}
        if current.get("positions") is not None:
            positions.append(restore_result(current["positions"], MaintenancePositions))
        state = snapshot.get("promotion_state") or {}
        if state.get("declared"):
            promotion[row.repo] = [
                {
                    "target": target["name"],
                    "destination": target["destination"],
                    "state": target["state"],
                    "accepted": target["accepted"],
                    "proven": state.get("proven", ""),
                    "door_ref": target["door_ref"],
                }
                for target in state.get("targets", [])
            ]
    for row in observations.runs:
        repo = str(row.repository or "")
        if (
            repo
            and row.kind == "maintenance"
            and row.maintenance_act
            and row.phase in ("Running", "Pending")
        ):
            running.setdefault(repo, []).append(
                {"act": row.maintenance_act, "ticket": row.ticket}
            )
    return [
        asdict(item)
        for item in derive_inbox(
            positions, running=running, promotion=promotion, hidden_repos=hidden
        )
    ]
