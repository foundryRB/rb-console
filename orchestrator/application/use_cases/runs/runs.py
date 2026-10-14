"""Read the run inventory observed by background collection."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


class Runs:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self, *, viewer: CommandContext | None = None) -> list[RunInventoryEntry]:
        return [
            run
            for run in self.observations.runs
            if viewer is None or viewer.sees(run.repository)
        ]
