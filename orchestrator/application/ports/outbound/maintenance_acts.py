"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.comment_created import CommentCreated
from orchestrator.domain.model.issue_closed import IssueClosed
from orchestrator.domain.model.pull_merge_result import PullMergeResult

__all__ = ["MaintenanceActs"]


class MaintenanceActs(Protocol):
    """Writes for the maintenance mode, each byte-identical to the gh command a human
    would run, under the console-role git identity; refuses without a credential
    (INT-FC-R61). The engine calls merge only over a recorded PASS (INT-FC-R65)."""

    def merge(self, repo: str, number: int, *, expected_head: str = "") -> PullMergeResult:
        """Merge a PR as ``gh pr merge --rebase`` does (rebase and fast-forward)."""
        ...

    def comment(self, repo: str, number: int, body: str) -> CommentCreated:
        """Comment on an issue or PR as ``gh issue comment`` does."""
        ...

    def close_issue(self, repo: str, number: int) -> IssueClosed:
        """Close an issue as ``gh issue close`` does: the operator's act when a merged PR
        did not auto-close its ticket."""
        ...

    def label(self, repo: str, number: int, label: str) -> None:
        """Add a label to an issue as ``gh issue edit --add-label`` does (additive): the
        operator's act when switching an over-scope ticket to a delivery line hides it with
        ``foundry-hidden`` (INT-FC-R100)."""
        ...
