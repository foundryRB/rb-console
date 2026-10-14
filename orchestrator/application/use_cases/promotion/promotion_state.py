"""Read promotion state from its observed snapshot."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


class PromotionState:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self, repo: str) -> dict:
        result = dict(
            self.observations.metadata.get(repo, {}).get(
                "promotion_state",
                {
                    "repo": repo,
                    "declared": False,
                    "problem": "Observation pending",
                    "proven": "",
                    "targets": [],
                },
            )
        )
        return result
