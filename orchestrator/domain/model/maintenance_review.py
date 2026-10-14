"""MaintenanceReview semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceReview:
    author: str = ""
    association: str = ""
    state: str = ""
    body: str = ""
    submitted_at: str = ""
