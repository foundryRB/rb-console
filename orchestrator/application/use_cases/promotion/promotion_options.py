"""Read promotion options from its observed snapshot."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


class PromotionOptions:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self, repo: str) -> dict:
        result = dict(
            self.observations.metadata.get(repo, {}).get(
                "promotion_options", {"repo": repo, "readable": False, "installs": []}
            )
        )
        return result
