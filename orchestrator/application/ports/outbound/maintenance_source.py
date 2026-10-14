"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.maintenance_check import MaintenanceCheck
from orchestrator.domain.model.maintenance_comment import MaintenanceComment
from orchestrator.domain.model.maintenance_file import MaintenanceFile
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.maintenance_release import MaintenanceRelease
from orchestrator.domain.model.maintenance_review import MaintenanceReview

__all__ = ["MaintenanceSource"]


class MaintenanceSource(Protocol):
    """Authoritative repo-host records for observation and command preflight.

    Empty collections describe successful reads. An unavailable source raises
    SourceUnavailable so callers can retain their previous observation.
    """

    def repository_revision(self, repo: str) -> str:
        """Resolve the authoritative default branch commit."""
        ...

    def open_issues(self, repo: str) -> tuple[MaintenanceIssue, ...]:
        """Open issues (the intent records); PRs wearing issue clothes included."""
        ...

    def open_prs(self, repo: str) -> tuple[MaintenancePullRequest, ...]:
        """Open PRs (the review records)."""
        ...

    def closed_prs(self, repo: str) -> tuple[MaintenancePullRequest, ...]:
        """Recently-closed PRs (merged and closed-unmerged), newest first, so a ticket whose
        resolve PR has left the open list resolves to merged (done) or closed (re-drive)."""
        ...

    def pr_files(self, repo: str, number: int) -> tuple[MaintenanceFile, ...]:
        """The PR diff's actual content: changed files with patch text (INT-FC-R63)."""
        ...

    def pr_reviews(self, repo: str, number: int) -> tuple[MaintenanceReview, ...]:
        """Normalized reviewer identity, association, disposition, text and submission time."""
        ...

    def check_runs(self, repo: str, sha: str) -> tuple[MaintenanceCheck, ...]:
        """The commit's check runs, for the checks state."""
        ...

    def default_branch_checks(self, repo: str) -> tuple[MaintenanceCheck, ...]:
        """The DEFAULT branch head's check runs, folded by the same rule as a PR's so the
        train can say whether the branch that ships is red."""
        ...

    def tags(self, repo: str) -> list[str]:
        """Tag names, newest first (the release train's version-now)."""
        ...

    def releases(self, repo: str) -> tuple[MaintenanceRelease, ...]:
        """Published releases (tag, name, date, url)."""
        ...

    def unreleased_subjects(self, repo: str) -> list[str]:
        """Commit subjects on the default branch since the latest semver tag."""
        ...

    def issue(self, repo: str, number: int) -> MaintenanceIssue:
        """One issue with normalized author, labels, type and content."""
        ...

    def pr(self, repo: str, number: int) -> MaintenancePullRequest:
        """One pull request with its author and immutable head revision."""
        ...

    def issue_comments(self, repo: str, number: int) -> tuple[MaintenanceComment, ...]:
        """An issue's comment text, so the console can read a
        delivery-scale prompt back off a marked comment the resolve skill left (INT-FC-R100),
        and a Managed ticket's home-PR pointer off the marker its resolve left (INT-FC-R135)."""
        ...
