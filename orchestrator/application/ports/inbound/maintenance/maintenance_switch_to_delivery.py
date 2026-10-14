"""MaintenanceSwitchToDelivery application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class MaintenanceSwitchToDeliveryPort(Protocol):
    def execute(
        self,
        repo: str,
        number: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict: ...
