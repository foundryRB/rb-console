"""MaintenanceInbox over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.domain.model.command_context import CommandContext


class MaintenanceInbox:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(
        self, include_hidden: bool = False, *, viewer: CommandContext | None = None
    ) -> dict:
        """The fleet inbox, served from the warm cache (INT-FC-R68): the background
        refresher derives it org-wide; a page read never fans out to GitHub. Two hides
        are excluded by default, both the Fleet's repo-topic hide (INT-FC-R47) carried
        onto the queue: a ticket carrying the 'foundry-hidden' LABEL, at issue scope
        (INT-FC-R96), and every row of a repo carrying the 'foundry-hidden' TOPIC, at
        repo scope (INT-FC-R155). include_hidden reveals both. A viewer reads only the
        rows of the repositories it sees."""
        items = (
            self.observations.inbox
            if include_hidden
            else [it for it in self.observations.inbox if not it.get("hidden")]
        )
        if viewer is not None:
            items = [it for it in items if viewer.sees(it.get("repo"))]
        return {"items": items, "scanned": self.observations.inbox_tick > 0}
