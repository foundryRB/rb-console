"""MaintenanceRelease semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceRelease:
    tag: str = ""
    name: str = ""
    published_at: str = ""
    url: str = ""
