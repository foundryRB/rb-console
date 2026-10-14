"""ListAgents application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class ListAgentsPort(Protocol):
    def execute(self, *, viewer: CommandContext | None = None) -> list[dict]: ...
