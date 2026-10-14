"""Fleet over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.fleet_item import FleetItem


class Fleet:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(
        self, include_hidden: bool = False, *, viewer: CommandContext | None = None
    ) -> list[FleetItem]:
        """The whole floor: every project with its delivery, onboarding, and live status.
        Repos carrying the 'foundry-hidden' topic (CI, libraries, ...) are excluded unless
        include_hidden. Served from the warm cache, refreshed out of band. A viewer
        reads only the projects it sees."""
        items = [
            item
            for item in self.observations.fleet
            if viewer is None or viewer.sees(item.repo)
        ]
        return items if include_hidden else [i for i in items if not i.hidden]
