"""Read observed run status without executor traffic."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


class RunStatus:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self, handle: str) -> str:
        return (
            self.observations.metadata.get("", {})
            .get("statuses", {})
            .get(handle, "unknown")
        )
