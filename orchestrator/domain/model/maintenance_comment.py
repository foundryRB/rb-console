"""MaintenanceComment semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceComment:
    body: str = ""
