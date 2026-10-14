"""MaintenanceActs over the GitHub API (INT-FC-R61): the writes the console causes,
each byte-identical to the gh command a human would run, executed under the shared
git identity (fc-git). The OIDC-gated press is the operator's; this adapter refuses
outright when no git credential is configured - a write never silently no-ops.

Also the GitCredentialCheck (INT-FC-R142): the save-time preflight for a git identity's
PAT. One adapter serving two ports because both are this console talking to the repo host
over the same API - the ports stay separate because a read that exercises a candidate
credential is not a write the operator caused.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.comment_created import CommentCreated
from orchestrator.domain.model.issue_closed import IssueClosed
from orchestrator.domain.model.pull_merge_result import PullMergeResult


class GitHubActs:
    _API = "https://api.github.com"

    def __init__(self, org: str, token_provider, *, transport: GitHubTransport | None = None, inventory_provider=None) -> None:
        self._transport = transport or GitHubTransport()
        self._inventory_provider = inventory_provider
        self._org = org
        self._token_provider = token_provider

    def merge(self, repo: str, number: int, expected_head: str = "") -> PullMergeResult:
        """Merge a PR exactly as ``gh pr merge --rebase`` does: the same endpoint and
        payload semantics (PUT /pulls/{n}/merge, merge_method=rebase), so the PR's
        commits land individually on the default branch - no merge commit, no
        constructed title, and the changelog stays granular per commit."""
        data = self._req(
            "PUT",
            f"/repos/{self._full(repo)}/pulls/{number}/merge",
            {"merge_method": "rebase", **({"sha": expected_head} if expected_head else {})},
        )
        if not isinstance(data, dict) or not isinstance(data.get("merged"), bool):
            raise SourceUnavailable("merge acknowledgement is malformed")
        if any(not isinstance(data.get(key, ""), str) for key in ("sha", "message")):
            raise SourceUnavailable("merge acknowledgement is malformed")
        return PullMergeResult(data["merged"], data.get("sha", ""), data.get("message", ""))

    def comment(self, repo: str, number: int, body: str) -> CommentCreated:
        """Comment on an issue or PR exactly as ``gh issue comment`` / ``gh pr comment``
        do (POST /issues/{n}/comments; PRs are issues to that endpoint)."""
        data = self._req(
            "POST",
            f"/repos/{self._full(repo)}/issues/{number}/comments",
            {"body": body},
        )
        if not isinstance(data, dict) or not isinstance(data.get("id"), int) or isinstance(data.get("id"), bool) or data["id"] <= 0 or not isinstance(data.get("html_url", ""), str):
            raise SourceUnavailable("comment acknowledgement is malformed")
        return CommentCreated(data["id"], data.get("html_url", ""))

    def close_issue(self, repo: str, number: int) -> IssueClosed:
        """Close an issue exactly as ``gh issue close`` does (PATCH /issues/{n}, state=closed).
        The operator's act when a merged PR did not auto-close its ticket."""
        data = self._req(
            "PATCH",
            f"/repos/{self._full(repo)}/issues/{number}",
            {"state": "closed"},
        )
        if not isinstance(data, dict) or data.get("number") != number or data.get("state") != "closed":
            raise SourceUnavailable("ticket closure acknowledgement is malformed")
        return IssueClosed(number)

    def label(self, repo: str, number: int, label: str) -> None:
        """Add a label to an issue exactly as ``gh issue edit --add-label`` does
        (POST /issues/{n}/labels, {labels:[...]}). Additive - it appends to the labels
        already on the ticket, never replacing them - so hiding a switched-to-delivery
        ticket with foundry-hidden keeps its other labels intact (INT-FC-R100)."""
        data = self._req(
            "POST",
            f"/repos/{self._full(repo)}/issues/{number}/labels",
            {"labels": [label]},
        )
        if not isinstance(data, list) or not any(isinstance(row, dict) and row.get("name") == label for row in data):
            raise SourceUnavailable("label acknowledgement is malformed")

    def validate_identity(self, token: str, login: str = "") -> tuple[bool | None, str]:
        """GitCredentialCheck: exercise a PAT against GET /user before it is seated.

        Deliberately NOT routed through _req: that reads the seated token from the provider
        and POSTs a body, while this must exercise a candidate token that is not stored yet -
        the same reason DriverAgent.validate takes its credential as an argument.
        """
        token = (token or "").strip()
        if not token:
            return False, "no token given"
        req = urllib.request.Request(
            f"{self._API}/user",
            method="GET",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        try:
            with self._transport.request(req, timeout=20) as resp:
                data = json.loads(resp.read() or b"{}")
                # GitHub returns this only for a PAT that carries an expiry; a classic
                # never-expiring token simply omits it, so its absence is not a finding.
                expiry = resp.headers.get("github-authentication-token-expiration") or ""
        except SourceUnavailable as exc:
            cause = exc.__cause__
            if isinstance(cause, urllib.error.HTTPError):
                headers = {str(key).lower(): str(value) for key, value in (cause.headers or {}).items()}
                rate_limited = "retry-after" in headers or headers.get("x-ratelimit-remaining") == "0"
                if cause.code == 401 or (cause.code == 403 and not rate_limited):
                    return False, f"GitHub rejected the token ({cause.code})"
            return None, "GitHub gave no usable answer"
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return False, f"GitHub rejected the token ({exc.code})"
            # Any other status is GitHub having a bad day, not a verdict on the token.
            return None, f"GitHub answered {exc.code}"
        except urllib.error.URLError as exc:
            return None, f"GitHub unreachable: {exc.reason}"
        except (TimeoutError, ValueError) as exc:  # timeout, or a body that is not JSON
            return None, f"GitHub gave no usable answer ({exc})"
        actual = str(data.get("login") or "")
        if login.strip() and actual and actual.lower() != login.strip().lower():
            return False, f"the token authenticates as {actual}, not {login.strip()}"
        return True, f"authenticates as {actual or 'an unnamed account'}" + (f", expires {expiry}" if expiry else "")

    def _full(self, repo: str) -> str:
        return repo if "/" in repo else f"{self._org}/{repo}"

    def _req(self, method: str, path: str, body: dict):
        token = self._token_provider() or ""
        if not token:
            raise RuntimeError("no git credential configured; set it in the Console settings")
        req = urllib.request.Request(
            f"{self._API}{path}",
            data=json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self._transport.request(req, timeout=20) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            # GitHub refusing an act (405 not mergeable, 409 conflict, ...) is an
            # answer, not a crash: surface its own message to the operator's pane.
            try:
                detail = json.loads(exc.read() or b"{}").get("message", "")
            except Exception:  # noqa: BLE001
                detail = ""
            raise RuntimeError(f"GitHub refused ({exc.code}): {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub unreachable: {exc.reason}") from exc
        return json.loads(raw) if raw else {}
