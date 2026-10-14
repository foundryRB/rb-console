"""CloseLine application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState


@runtime_checkable
class CloseLinePort(Protocol):
    def execute(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState: ...
