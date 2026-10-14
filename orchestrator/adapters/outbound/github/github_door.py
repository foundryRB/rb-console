"""Normalize home repository evidence read using its named pair credential."""

from __future__ import annotations

from orchestrator.adapters.outbound.github import maintenance_evidence as evidence
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest


class GitHubDoor:
    """A door onto github.com, performed on a named pair credential."""

    _API = "https://api.github.com"

    def __init__(
        self, pair_token_provider, *, transport: GitHubTransport | None = None
    ) -> None:
        self._transport = transport or GitHubTransport()
        # callable: the contract-declared credential NAME -> its value, resolved
        # server-side. The value never leaves this process by any other path.
        self._pair_token_provider = pair_token_provider

    def repository_revision(self, repo: str, branch: str, credential: str) -> str:
        from urllib.parse import quote

        from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

        if not branch:
            info = self._dict(f"/repos/{repo}", credential)
            branch = info.get("default_branch", "")
        if not branch:
            raise SourceUnavailable("repository home branch is unavailable")
        data = self._dict(
            f"/repos/{repo}/git/ref/heads/{quote(branch, safe='')}", credential
        )
        sha = (data.get("object") or {}).get("sha", "")
        if not sha:
            raise SourceUnavailable("repository home revision is unavailable")
        return sha

    def pull_request(
        self, repo: str, number: int, credential: str
    ) -> MaintenancePullRequest | None:
        """One pull request on the pair's repository, with its reviews and its head's check
        runs folded in under ``reviews`` and ``check_runs`` - the three reads the loop
        derives a PR's position from, taken as one so a Managed ticket costs the pair
        exactly one PR's worth of reads and never a listing."""
        pr = self._dict(f"/repos/{repo}/pulls/{number}", credential)
        if not pr:
            return None
        pr["reviews"] = self._list(f"/repos/{repo}/pulls/{number}/reviews", credential)
        sha = (pr.get("head") or {}).get("sha") or ""
        runs = (
            self._dict(f"/repos/{repo}/commits/{sha}/check-runs", credential)
            if sha
            else {}
        )
        checks = evidence._list(runs, "check_runs")
        if evidence._integer(runs, "total_count") > len(checks):
            checks = [*checks, {"status": "in_progress", "conclusion": None}]
        pr["check_runs"] = checks
        return evidence.pull_request(pr)

    def open_pull_requests(
        self, repo: str, base: str, credential: str
    ) -> tuple[MaintenancePullRequest, ...] | None:
        """The open pull requests against ``base``. The pair's repo is a full ``owner/name``
        outside our org, so it is read as given rather than prefixed with ours."""
        rows = self._maybe_list(
            f"/repos/{repo}/pulls?state=open&base={base}&per_page=100", credential
        )

        return (
            None if rows is None else tuple(evidence.pull_request(row) for row in rows)
        )

    def closed_pull_requests(
        self, repo: str, base: str, credential: str
    ) -> tuple[MaintenancePullRequest, ...] | None:
        """The recently-closed pull requests against ``base``, merged ones carrying
        ``merged_at``."""
        rows = self._maybe_list(
            f"/repos/{repo}/pulls?state=closed&base={base}&per_page=100", credential
        )

        return (
            None if rows is None else tuple(evidence.pull_request(row) for row in rows)
        )

    # -- plumbing -----------------------------------------------------------------

    def _maybe_list(self, path: str, credential: str) -> list[dict] | None:
        data = self._get(path, credential)
        if data is None:
            return None
        if not isinstance(data, list):
            raise SourceUnavailable("Invalid home pull request collection")
        return data

    def _list(self, path: str, credential: str) -> list:
        data = self._get(path, credential)
        if not isinstance(data, list):
            raise SourceUnavailable("Invalid home review collection")
        return data

    def _dict(self, path: str, credential: str) -> dict:
        data = self._get(path, credential)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise SourceUnavailable("Invalid home pull request record")
        return data

    def _get(self, path: str, credential: str):
        token = (self._pair_token_provider(credential) if credential else "") or ""
        return self._transport.json(f"{self._API}{path}", token, paginate=True)
