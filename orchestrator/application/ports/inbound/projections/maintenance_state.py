"""MaintenanceState application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MaintenanceStatePort(Protocol):
    def execute(self, repo: str, include_hidden: bool = False) -> dict: ...
