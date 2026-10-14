"""ListTeams application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class ListTeamsPort(Protocol):
    def execute(self, *, viewer: CommandContext) -> dict: ...
