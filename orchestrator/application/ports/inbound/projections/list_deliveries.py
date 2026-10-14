"""ListDeliveries application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext

from orchestrator.domain.model.delivery_state import DeliveryState


@runtime_checkable
class ListDeliveriesPort(Protocol):
    def execute(self, *, viewer: CommandContext | None = None) -> list[DeliveryState]: ...
