"""PrPosition domain value."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.maintenance import CHECKS_UNKNOWN, VERDICT_AWAITING


@dataclass(frozen=True)
class PrPosition:
    """One PR: the review record. The verdict and checks are derived, never stored;
    contributor marks the fresh-eyes rule's other half (a PR authored by anyone but one of
    the console's own identities always takes the gated path). ``state`` is 'open' for a live review
    record; a resolve's PR that has since left the open list carries 'merged' (the work
    landed) or 'closed' (closed unmerged), so the lifecycle can tell done from re-drive."""

    number: int
    title: str
    author: str
    head: str = ""
    head_sha: str = ""
    body: str = ""
    url: str = ""
    verdict: str = VERDICT_AWAITING
    checks: str = CHECKS_UNKNOWN
    contributor: bool = False
    updated_at: str = ""
    state: str = "open"  # 'open' | 'merged' | 'closed'
