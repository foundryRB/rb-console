"""Authoritative maintenance evidence normalized from GitHub wire responses."""

from __future__ import annotations

from orchestrator.adapters.outbound.github import maintenance_evidence as evidence
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.maintenance_check import MaintenanceCheck
from orchestrator.domain.model.maintenance_comment import MaintenanceComment
from orchestrator.domain.model.maintenance_file import MaintenanceFile
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.maintenance_release import MaintenanceRelease
from orchestrator.domain.model.maintenance_review import MaintenanceReview


class GitHubMaintenanceSource:
    _API = "https://api.github.com"

    def __init__(
        self,
        org: str,
        token_provider,
        *,
        transport: GitHubTransport | None = None,
        inventory_provider=None,
    ) -> None:
        self._transport = transport or GitHubTransport()
        self._inventory_provider = inventory_provider
        self._org = org
        self._token_provider = token_provider  # callable -> the live git token
        # Install-side only. The one read that leaves our org - a Managed ticket's pull
        # request on its home - is the Door's (#167), so nothing here resolves a pair
        # credential and nothing here reaches another organisation.

    # -- reads (each degrades to its empty shape, never raises) ------------------

    def open_issues(self, repo: str) -> tuple[MaintenanceIssue, ...]:
        """Open issues (PRs wearing issue clothes included; the resolver filters them)."""
        return tuple(
            evidence.issue(item)
            for item in self._list(
                f"/repos/{self._full(repo)}/issues?state=open&per_page=100"
            )
        )

    def repository_revision(self, repo: str) -> str:
        from urllib.parse import quote

        from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

        full = repo if "/" in repo else f"{self._org}/{repo}"
        info = self._get(f"/repos/{full}")
        branch = info.get("default_branch")
        if not branch:
            raise SourceUnavailable("default branch is unavailable")
        data = self._get(f"/repos/{full}/git/ref/heads/{quote(branch, safe='')}")
        sha = (data.get("object") or {}).get("sha", "")
        if not sha:
            raise SourceUnavailable("repository revision is unavailable")
        return sha

    def open_prs(self, repo: str) -> tuple[MaintenancePullRequest, ...]:
        return tuple(
            evidence.pull_request(item)
            for item in self._list(
                f"/repos/{self._full(repo)}/pulls?state=open&per_page=100"
            )
        )

    def closed_prs(self, repo: str) -> tuple[MaintenancePullRequest, ...]:
        """The most-recently-updated closed PRs (merged and closed-unmerged), newest first.
        Each carries ``merged_at`` (null when closed unmerged), so the lifecycle can tell a
        landed resolve PR from a rejected one. Bounded - only recent ones matter for a still
        open ticket."""
        return tuple(
            evidence.pull_request(item)
            for item in self._list(
                f"/repos/{self._full(repo)}/pulls?state=closed&sort=updated&direction=desc&per_page=30"
            )
        )

    def pr_files(self, repo: str, number: int) -> tuple[MaintenanceFile, ...]:
        """The diff's actual content: changed files with patch text (a link out is
        not substance)."""
        return tuple(
            evidence.changed_file(item)
            for item in self._list(
                f"/repos/{self._full(repo)}/pulls/{number}/files?per_page=100"
            )
        )

    def pr_reviews(self, repo: str, number: int) -> tuple[MaintenanceReview, ...]:
        return tuple(
            evidence.review(item)
            for item in self._list(
                f"/repos/{self._full(repo)}/pulls/{number}/reviews?per_page=100"
            )
        )

    def check_runs(self, repo: str, sha: str) -> tuple[MaintenanceCheck, ...]:
        if not sha:
            return ()
        data = self._dict(
            f"/repos/{self._full(repo)}/commits/{sha}/check-runs?per_page=100"
        )
        runs = evidence._list(data, "check_runs")
        # Fail-closed on pagination: a failing check beyond the first page must never
        # fold green, so an incomplete page reads as still-in-progress.
        if isinstance(data, dict) and evidence._integer(data, "total_count") > len(
            runs
        ):
            runs = [*runs, {"status": "in_progress", "conclusion": None}]
        return tuple(evidence.check(item) for item in runs)

    def default_branch_checks(self, repo: str) -> tuple[MaintenanceCheck, ...]:
        """The default branch head's check runs. GitHub's check-runs endpoint takes any ref,
        so the branch name is the read - no separate head-sha lookup - and the pagination
        fail-closed rule above applies unchanged."""
        info = self._dict(f"/repos/{self._full(repo)}")
        return self.check_runs(
            repo, (info.get("default_branch") or "main") if info else "main"
        )

    def tags(self, repo: str) -> list[str]:
        return [
            t.get("name", "")
            for t in self._list(f"/repos/{self._full(repo)}/tags?per_page=100")
        ]

    def releases(self, repo: str) -> tuple[MaintenanceRelease, ...]:
        return tuple(
            evidence.release(item)
            for item in self._list(f"/repos/{self._full(repo)}/releases?per_page=20")
        )

    def unreleased_subjects(self, repo: str) -> list[str]:
        """FULL commit messages on the default branch since the latest semver tag
        (the train reads the subject line AND any BREAKING CHANGE footer, exactly as
        the release tooling does); [] when there is no tag yet (a first release is a
        delivery concern, not a train)."""
        full = self._full(repo)
        tag_names = self.tags(repo)
        from orchestrator.application.release_train import latest_version

        version = latest_version(tag_names)
        if not version:
            return []
        # the tag may carry a leading v; find the actual name that parses to version
        tag = next((t for t in tag_names if t.lstrip("v") == version), f"v{version}")
        info = self._dict(f"/repos/{full}")
        branch = info.get("default_branch", "main") if info else "main"
        data = self._dict(f"/repos/{full}/compare/{tag}...{branch}")
        commits = data.get("commits", []) if isinstance(data, dict) else []
        return [((c.get("commit") or {}).get("message") or "") for c in commits]

    def issue(self, repo: str, number: int) -> MaintenanceIssue:
        return evidence.issue(self._dict(f"/repos/{self._full(repo)}/issues/{number}"))

    def pr(self, repo: str, number: int) -> MaintenancePullRequest:
        return evidence.pull_request(
            self._dict(f"/repos/{self._full(repo)}/pulls/{number}")
        )

    def issue_comments(self, repo: str, number: int) -> tuple[MaintenanceComment, ...]:
        """An issue's comments, oldest first (GitHub's default order), each carrying a
        ``body`` - so the console reads a delivery-scale prompt back off the marked comment
        the resolve skill left on the ticket (INT-FC-R100). Degrades to [] like every read."""
        return tuple(
            evidence.comment(item)
            for item in self._list(
                f"/repos/{self._full(repo)}/issues/{number}/comments?per_page=100"
            )
        )

    # -- plumbing -----------------------------------------------------------------

    def _full(self, repo: str) -> str:
        return repo if "/" in repo else f"{self._org}/{repo}"

    def _list(self, path: str) -> list:
        data = self._get(path)
        if not isinstance(data, list):
            raise SourceUnavailable("Invalid maintenance source collection")
        return data

    def _dict(self, path: str) -> dict:
        data = self._get(path)
        if not isinstance(data, dict):
            raise SourceUnavailable("Invalid maintenance source record")
        return data

    def _get(self, path: str):
        token = self._token_provider() or ""
        return self._transport.json(
            f"https://api.github.com{path}", token, paginate=True
        )
