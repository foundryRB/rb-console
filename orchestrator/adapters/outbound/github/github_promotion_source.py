"""Read an app's promotion facts off OUR OWN repo host: its contract, and what each
declared environment target currently carries.

Everything the promotion mode shows is a file in git or a pull request on the
host (REF-Promotion section 5: the record IS git), so this adapter only reads
and never derives: the contract text off the default branch, and an environment's
pinned version off the app's own ``deploy-<install>`` branch. Every read degrades to
None or empty on an unreadable target, which the derivation reports as
unreadable rather than guessing a state.

A pair's own repository is NOT read here. Reaching another organisation is the Door's
(#167, ADR-044 section 6): it is a different seam, selected per app from the credential
that pair granted us, and keeping its reads beside these install-side ones is exactly the
entanglement that carve undid.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from orchestrator.adapters.outbound.github.blob_text import blob_text
from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

CONTRACT_PATH = "devops/promotion.yaml"


class GithubPromotionSource:
    """The repo-host half of the promotion mode's reads, install-side only."""

    def __init__(self, org: str, token_provider, *, transport: GitHubTransport | None = None, inventory_provider=None) -> None:
        self._transport = transport or GitHubTransport()
        self._inventory_provider = inventory_provider
        self._org = org
        self._token_provider = token_provider

    def contract_text(self, repo: str, *, revision: str = "") -> str | None:
        """The app's promotion contract off its default branch; None when the repo
        carries none (an app that declares no targets promotes nowhere) or is
        unreadable."""
        return self._file_text(repo, ref=revision, path=CONTRACT_PATH)

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

    def environment_values(self, repo: str, install: str, environment: str) -> str | None:
        """The values file of one environment on the app's deploy branch for that
        install; None when the branch, the folder or the file is absent."""
        return self._file_text(
            repo, ref=f"deploy-{install}", path=f"{environment}/values.yaml"
        )

    def deploy_installs(self, repo: str) -> dict[str, list[str]]:
        """Each install this app is onboarded to, with the environment folders its
        deploy branch carries: read from the app's OWN repo, so declaring a target
        needs nothing from the platform and offers nothing that does not exist.

        {} when the repo is unreadable, which the caller reports rather than
        offering an empty choice as though the app had no installs."""
        full = repo if "/" in repo else f"{self._org}/{repo}"
        branches = self._get(f"/repos/{full}/branches?per_page=100")
        if not isinstance(branches, list):
            return {}
        found: dict[str, list[str]] = {}
        for branch in branches:
            name = str((branch or {}).get("name") or "")
            if not name.startswith("deploy-"):
                continue
            install = name[len("deploy-"):]
            tree = self._get(f"/repos/{full}/git/trees/{name}?recursive=1")
            paths = [
                str(entry.get("path") or "")
                for entry in ((tree or {}).get("tree") or [])
                if isinstance(entry, dict)
            ]
            found[install] = sorted(
                {
                    path.split("/", 1)[0]
                    for path in paths
                    if path.count("/") == 1 and path.endswith("/values.yaml")
                }
            )
        return found

    def write_contract(self, repo: str, text: str, message: str, author: str = "", *, expected_revision: str) -> str:
        from urllib.parse import quote

        from orchestrator.domain.exceptions.conflict import Conflict
        full = repo if "/" in repo else f"{self._org}/{repo}"
        info = self._get(f"/repos/{full}")
        branch = info.get("default_branch", "")
        if not expected_revision or self.repository_revision(repo) != expected_revision:
            raise Conflict("promotion contract revision changed")
        parent = self._get(f"/repos/{full}/git/commits/{quote(expected_revision, safe='')}")
        tree = self._put(f"/repos/{full}/git/trees", {"base_tree": parent["tree"]["sha"], "tree": [{"path": CONTRACT_PATH, "mode": "100644", "type": "blob", "content": text}]}, method="POST")
        body = {"message": message, "tree": tree["sha"], "parents": [expected_revision]}
        if author:
            body["author"] = {"name": author, "email": f"{author}@users.noreply.github.com"}
        commit = self._put(f"/repos/{full}/git/commits", body, method="POST")
        self._put(f"/repos/{full}/git/refs/heads/{quote(branch, safe='')}", {"sha": commit["sha"], "force": False}, method="PATCH")
        return commit["sha"]

    def _put(self, path: str, body: dict, *, method: str = "PUT"):
        token = self._token_provider() or ""
        if not token:
            raise RuntimeError("no git credential configured; set it in the Console settings")
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            data=json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "foundry-console",
            },
        )
        try:
            with self._transport.request(request, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            if error.code in {409, 422}:
                from orchestrator.domain.exceptions.conflict import Conflict
                raise Conflict("promotion contract revision changed") from error
            try:
                detail = json.loads(error.read() or b"{}").get("message", "")
            except SourceUnavailable:
                raise
            except (ValueError, UnicodeError, TypeError):
                detail = ""
            raise RuntimeError(f"GitHub refused ({error.code}): {detail or error.reason}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"GitHub unreachable: {error.reason}") from error
        return json.loads(raw) if raw else {}

    def probe(self, url: str) -> bool | None:
        """Whether a declared probe URL answers. None when it was not reachable at
        all, which the derivation keeps distinct from a live 'no'."""
        if not url:
            return None
        request = urllib.request.Request(
            url, headers={"Cache-Control": "no-cache", "User-Agent": "foundry-console"}
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return 200 <= response.status < 400
        except urllib.error.HTTPError as error:
            return 200 <= error.code < 400
        except SourceUnavailable:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            return None

    def read_suite(self, url: str, match: str = "") -> bool | None:
        """The verdict a suite publishes, read and never dispatched.

        A probe and a suite ask different questions through the same pipe. A probe
        asks whether the target is there, and the HTTP status is the answer. A
        suite asks whether it passed, and the status is only transport: a pipeline
        publishes a failure as a healthy 200, so reading the status alone would
        call a red suite green.

        So a declared ``match`` is what says passing, and an answer that does not
        carry it is UNREADABLE rather than green. That is conservative on purpose:
        with only a pass rule we cannot tell a real failure from a response shape
        we do not understand, and unchecked is not proven either way.
        """
        if not url:
            return None
        request = urllib.request.Request(
            url, headers={"Cache-Control": "no-cache", "User-Agent": "foundry-console"}
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                if not 200 <= response.status < 300:
                    return None
                if not match:
                    # Nothing declared: the endpoint is a pass/fail surface of its
                    # own, so answering at all is the verdict.
                    return True
                body = response.read(200_000).decode("utf-8", "replace")
        except SourceUnavailable:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
        return True if match in body else None

    # -- plumbing -----------------------------------------------------------------

    def _file_text(self, repo: str, *, ref: str, path: str) -> str | None:
        full = repo if "/" in repo else f"{self._org}/{repo}"
        query = f"?ref={ref}" if ref else ""
        try:
            blob = self._get(f"/repos/{full}/contents/{path}{query}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if not isinstance(blob, dict) or "content" not in blob:
            raise SourceUnavailable("promotion file content is malformed")
        try:
            return blob_text(blob)
        except SourceUnavailable:
            raise
        except (ValueError, TypeError, AttributeError) as exc:
            raise SourceUnavailable("promotion file content is malformed") from exc

    def _get(self, path: str):
        token = self._token_provider() or ""
        return self._transport.json(f"https://api.github.com{path}", token, paginate=True)
