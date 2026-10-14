"""GitHub commands reject moved heads and publish one revision-sensitive commit."""
from __future__ import annotations

from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE

import base64
from io import BytesIO
from urllib.error import HTTPError

import pytest

from orchestrator.adapters.outbound.github.github_acts import GitHubActs
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.domain.exceptions.conflict import Conflict


def test_merge_sends_the_authorized_pull_request_head() -> None:
    seen = []
    acts = GitHubActs("org", lambda: "token")
    acts._req = lambda method, path, body: seen.append(body) or {"merged": True}
    acts.merge("app", 7, expected_head="authorized-head")
    assert seen == [{"merge_method": "rebase", "sha": "authorized-head"}]


def test_reopen_uses_one_parent_bound_commit_and_rejects_concurrent_head_change() -> None:
    calls = []
    store = GitHubRepoStore("org", lambda: "token")
    store._reopened = lambda record, content: "reopened"

    def request(method, path, token, body=None):
        calls.append((method, path, body))
        if "matching-refs" in path:
            return [{"ref": "refs/heads/delivery/line", "object": {"sha": "authorized-head"}}]
        if "/contents/" in path:
            assert "ref=authorized-head" in path
            return {"content": base64.b64encode(b"record").decode()}
        if method == "GET" and "/git/commits/" in path:
            return {"tree": {"sha": "base-tree"}}
        if path.endswith("/git/trees"):
            return {"sha": "new-tree"}
        if path.endswith("/git/commits"):
            assert body["parents"] == ["authorized-head"]
            return {"sha": "new-commit"}
        if method == "PATCH":
            assert body == {"sha": "new-commit", "force": False}
            raise HTTPError(path, 422, "not fast forward", {}, BytesIO())
        raise AssertionError((method, path))

    store._req = request
    with pytest.raises(Conflict):
        store.reopen_gate("app", "design.md", expected_revision="authorized-head")
    assert not any(method == "PUT" for method, _, _ in calls)
    tree = next(body for method, path, body in calls if path.endswith("/git/trees"))
    assert tree["base_tree"] == "base-tree"
    assert tree["tree"] == [{"path": "design.md", "mode": "100644", "type": "blob", "content": "reopened"}]


@pytest.mark.parametrize("act", ["sign", "reopen", "close"])
def test_moved_scratch_head_refuses_before_a_mutation(act: str) -> None:
    writes = []
    store = GitHubRepoStore("org", lambda: "token")

    def request(method, path, token, body=None):
        if method != "GET":
            writes.append(method)
        if "matching-refs" in path:
            return [{"ref": "refs/heads/delivery/line", "object": {"sha": "newer-head"}}]
        raise AssertionError("The head mismatch must refuse before further source work")

    store._req = request
    with pytest.raises(Conflict):
        if act == "sign":
            store.write_gate("app", "design.md", "2026-10-05", expected_revision="authorized-head", definition=CURRENT_LIFECYCLE)
        elif act == "reopen":
            store.reopen_gate("app", "design.md", expected_revision="authorized-head")
        else:
            store.close_line("app", expected_revision="authorized-head")
    assert writes == []
