"""MaintenanceInbox application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class MaintenanceInboxPort(Protocol):
    def execute(
        self, include_hidden: bool = False, *, viewer: CommandContext | None = None
    ) -> dict: ...
