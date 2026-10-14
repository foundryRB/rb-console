"""FleetChat application capability."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class FleetChatPort(Protocol):

    def execute(
        self, message: str, history=None, *, viewer: CommandContext | None = None
    ) -> dict:
        ...
