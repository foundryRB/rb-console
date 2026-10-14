"""SetTargetSelection application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class SetTargetSelectionPort(Protocol):
    def execute(
        self,
        repo: str,
        agent: str,
        provider: str,
        base_url: str,
        model: str,
        timeout_seconds: int | None = None,
        *,
        seat: dict | None = None,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None: ...
