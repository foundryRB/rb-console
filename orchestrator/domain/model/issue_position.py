"""IssuePosition domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IssuePosition:
    """One open ticket: the intent record (REF-Maintenance section 6). ``complexity`` and
    ``priority`` are the author's own hints, derived on read from a clean marker in the issue
    body (the same convention idiom as the verdict line and GitHub's ``Closes #3``); "" when
    the ticket carries no marker, so the signal is invisible on a clean repo. ``type`` is the
    native GitHub Issue Type (org-level, e.g. Bug/Feature/Task), read straight from the issue
    payload rather than a marker, since GitHub owns that attribute already (INT-FC-R94). Like
    every position, all three are derived, never stored (INT-FC-R58/R93)."""

    number: int
    title: str
    author: str
    labels: tuple[str, ...] = ()
    url: str = ""
    created_at: str = ""
    complexity: str = ""  # one of COMPLEXITY_LEVELS, or "" (absent / unrecognised)
    priority: str = ""    # one of PRIORITY_LEVELS, or "" (absent / unrecognised)
    type: str = ""        # the native GitHub Issue Type name (org-level, e.g. Bug/Feature/Task), or ""
