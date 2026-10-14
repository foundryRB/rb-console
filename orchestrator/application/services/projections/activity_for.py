"""Projections shared orchestration over explicit contracts."""

from __future__ import annotations


def helper_activity_for(d, repo: str, acts: dict[str, str], known: bool) -> str | None:
    """The observed activity for this full repository, or unknown without a source."""
    if d is None or not known:
        return None
    return acts.get(repo, "idle")
