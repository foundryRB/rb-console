"""TargetKind domain value."""
from __future__ import annotations

from enum import Enum


class TargetKind(str, Enum):
    """What a declared destination is. ENVIRONMENT is a manual environment of an
    install we run, written by a commit to that install's deploy branch; the next
    environment of this install and an environment of another install are the same
    act, differing only in which branch the commit lands on. REPOSITORY is another
    organization's repo, written by a pull request theirs to merge."""

    ENVIRONMENT = "environment"
    REPOSITORY = "repository"
