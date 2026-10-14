"""MaintenancePositions domain value."""
from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.domain.model.issue_position import IssuePosition
from orchestrator.domain.model.pr_position import PrPosition
from orchestrator.domain.model.release_train import ReleaseTrain


@dataclass(frozen=True)
class MaintenancePositions:
    """One repo's whole loop, derived: issues are intent, PRs are review, the train is
    shipping. Stored nowhere; the derivation writes no file and keeps no store."""

    repo: str
    issues: tuple[IssuePosition, ...] = ()
    prs: tuple[PrPosition, ...] = ()
    train: ReleaseTrain = field(default_factory=ReleaseTrain)
    # Recently-closed PRs (merged or closed-unmerged), newest first, so the lifecycle can
    # resolve a ticket whose resolve PR has already left the open list - the merged happy
    # path reads as done, a closed-unmerged one as re-drive, instead of an ambiguous stall.
    recent_closed: tuple[PrPosition, ...] = ()
