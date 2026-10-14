"""Read the observed delivery inventory."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState


class ListDeliveries:
    def __init__(self, *, index: DeliveryIndex | None) -> None:
        self.index = index

    def execute(self, *, viewer: CommandContext | None = None) -> list[DeliveryState]:
        states = self.index.all() if self.index else []
        return [state for state in states if viewer is None or viewer.sees(state.repo)]
