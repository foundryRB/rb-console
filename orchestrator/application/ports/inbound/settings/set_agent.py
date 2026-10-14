"""SetAgent application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class SetAgentPort(Protocol):
    def execute(
        self,
        name: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        models: list[str] | None = None,
        *,
        level: str = "install",
        team: str = "",
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict: ...
