"""Runs application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext

from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


@runtime_checkable
class RunsPort(Protocol):
    def execute(self, *, viewer: CommandContext | None = None) -> list[RunInventoryEntry]: ...
