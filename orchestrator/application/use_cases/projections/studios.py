"""Studios over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.studios_index import (
    StudioStatusIndex,
)
from orchestrator.domain.model.studio_health import StudioHealth


class Studios:
    def __init__(self, *, studio_index: StudioStatusIndex | None) -> None:
        self.studio_index = studio_index

    def execute(self) -> list[StudioHealth]:
        """The org-wide 'view of everything': each connected studio's reachability and a
        headline fact. Served from the warm cache, refreshed out of band."""
        if self.studio_index is not None:
            return self.studio_index.health()
        return []
