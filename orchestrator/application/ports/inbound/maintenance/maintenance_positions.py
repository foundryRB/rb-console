"""MaintenancePositions application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.maintenance_positions import MaintenancePositions


@runtime_checkable
class MaintenancePositionsPort(Protocol):
    def execute(self, repo: str) -> MaintenancePositions: ...
