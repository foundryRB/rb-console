"""Read maintenance state from its observed snapshot."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


class MaintenanceState:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self, repo: str, include_hidden: bool = False) -> dict:
        result = dict(
            self.observations.metadata.get(repo, {}).get(
                "maintenance_state",
                {
                    "repo": repo,
                    "positions": None,
                    "action": {"acts": [], "modes": [], "default_mode": "gated"},
                    "delivery": {"status": "loading", "phase": None},
                    "driven": [],
                    "home": None,
                },
            )
        )
        if not include_hidden and result.get("positions") is not None:
            positions = dict(result.get("positions") or {})
            positions["issues"] = [
                i
                for i in positions.get("issues", [])
                if "foundry-hidden" not in (i.get("labels") or [])
            ]
            result["positions"] = positions
        return result
