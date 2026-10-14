"""MaintenanceCheck semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceCheck:
    status: str = ""
    conclusion: str | None = None
    name: str = ""
