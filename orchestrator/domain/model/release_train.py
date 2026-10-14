"""ReleaseTrain domain value."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.maintenance import CHECKS_UNKNOWN


@dataclass(frozen=True)
class ReleaseTrain:
    """The shipping concern's spine: version now (the latest semver tag), what sits
    unreleased on the default branch counted by Conventional Commit type, and the next
    version the pipeline would cut. No releasable commits = no next version."""

    version: str = ""
    unreleased_total: int = 0
    breaking: int = 0
    feat: int = 0
    fix: int = 0
    other: int = 0
    next_version: str = ""
    deployed: str = ""       # the running revision, when the cluster answers
    healthy: bool | None = None  # deployment health; None = signal absent, never guessed
    # The default branch's own checks, folded by the same rule as a PR's: a release that cut
    # a tag but never published its images leaves the branch that ships red.
    checks: str = CHECKS_UNKNOWN
