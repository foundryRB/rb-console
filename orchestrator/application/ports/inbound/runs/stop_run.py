"""StopRun application capability."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class StopRunPort(Protocol):

    def execute(self, handle: str, terminate: bool=False, *, context: CommandContext, operation_id: str, expected_revision: str | None=None) -> dict:
        ...
