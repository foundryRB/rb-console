"""MaintenanceFile semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceFile:
    filename: str = ""
    status: str = ""
    additions: int = 0
    deletions: int = 0
    patch: str = ""
