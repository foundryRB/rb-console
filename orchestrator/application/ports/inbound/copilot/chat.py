"""Chat application capability."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class ChatPort(Protocol):

    def execute(
        self,
        repo: str,
        phase: str,
        message: str,
        history=None,
        references=None,
        *,
        viewer: CommandContext | None = None,
    ) -> dict:
        ...
