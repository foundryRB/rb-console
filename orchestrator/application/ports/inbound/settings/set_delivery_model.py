"""SetDeliveryModel application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class SetDeliveryModelPort(Protocol):
    def execute(
        self,
        repo: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        timeout_seconds: int | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict: ...
