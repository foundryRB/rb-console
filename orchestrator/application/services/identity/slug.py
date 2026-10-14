"""Identity shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.domain.delivery import delivery_slug


def helper_slug(repo: str) -> str:
    """The delivery slug threaded through every studio (see domain.delivery_slug); one
    definition, so this match and the worker's launch pin the same key."""
    return delivery_slug(repo)
