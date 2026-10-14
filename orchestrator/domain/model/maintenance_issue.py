"""MaintenanceIssue semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceIssue:
    number: int
    title: str = ""
    body: str = ""
    author: str = ""
    labels: tuple[str, ...] = ()
    url: str = ""
    created_at: str = ""
    issue_type: str = ""
    is_pull_request: bool = False
    state: str = "open"
