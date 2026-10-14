"""FleetStaleness over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


class FleetStaleness:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self) -> tuple[str | None, str]:
        """Since when the board has been standing on a held cache, and why - (None, "")
        while it is current (INT-FC-R144). The board is allowed to be stale; it is not
        allowed to be stale SILENTLY, because a held board and a fresh one look identical
        and the operator acts on what they see."""
        return (
            self.observations.fleet_stale_since,
            self.observations.fleet_stale_reason,
        )
