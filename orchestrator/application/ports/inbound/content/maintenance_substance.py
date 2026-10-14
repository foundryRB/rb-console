"""MaintenanceSubstance application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MaintenanceSubstancePort(Protocol):
    def execute(self, repo: str, kind: str, id: int | None = None) -> dict: ...
