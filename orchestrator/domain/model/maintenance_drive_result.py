"""MaintenanceDriveResult semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.maintenance_mode import MaintenanceMode


@dataclass(frozen=True)
class MaintenanceDriveResult:
    run_id: str
    handle: str
    act: str
    mode: MaintenanceMode
