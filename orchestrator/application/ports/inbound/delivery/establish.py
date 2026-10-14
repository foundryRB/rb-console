"""Establish application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState


@runtime_checkable
class EstablishPort(Protocol):
    def execute(
        self,
        target: str,
        request: str = "",
        source: bytes | None = None,
        source_name: str = "",
        app_name: str = "",
        *,
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState: ...
