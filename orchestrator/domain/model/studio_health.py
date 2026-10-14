"""StudioHealth domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioHealth:
    """One studio's reachability and a headline fact, for the org-wide view."""

    studio: str
    reachable: bool
    detail: str = ""
    url: str | None = None
