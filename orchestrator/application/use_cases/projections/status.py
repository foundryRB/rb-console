"""Read a delivery exclusively from its observed snapshot."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.services.delivery_resolution import derive_from_records


class Status:
    def __init__(self, *, index: DeliveryIndex | None) -> None:
        self.index = index

    def execute(self, repo: str) -> DeliveryState:
        """A repository absent from a completed scan carries no delivery line; before the
        first scan completes its state is still loading."""
        cached = self.index.get(repo) if self.index else None
        if cached is not None:
            return cached
        if self.index is not None and self.index.scanned:
            return derive_from_records(repo, False, {})
        return DeliveryState(repo, False, "loading", None, None, None, None, (), ())
