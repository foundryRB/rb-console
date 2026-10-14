"""MaintenancePullRequest semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.maintenance_check import MaintenanceCheck
from orchestrator.domain.model.maintenance_review import MaintenanceReview


@dataclass(frozen=True)
class MaintenancePullRequest:
    number: int
    title: str = ""
    body: str = ""
    author: str = ""
    head_branch: str = ""
    head_sha: str = ""
    url: str = ""
    updated_at: str = ""
    state: str = "open"
    merged: bool = False
    reviews: tuple[MaintenanceReview, ...] = ()
    checks: tuple[MaintenanceCheck, ...] = ()
