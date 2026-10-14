"""Fleet application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext

from orchestrator.domain.model.fleet_item import FleetItem


@runtime_checkable
class FleetPort(Protocol):
    def execute(
        self, include_hidden: bool = False, *, viewer: CommandContext | None = None
    ) -> list[FleetItem]: ...
