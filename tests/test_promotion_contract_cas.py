import pytest
from orchestrator.adapters.outbound.github.github_promotion_source import GithubPromotionSource
from orchestrator.domain.exceptions.conflict import Conflict

class Source(GithubPromotionSource):
    def __init__(self, head="old"):
        super().__init__("org", lambda: "token")
        self.head = head
        self.writes = []
    def _get(self, path):
        if path.endswith("/git/commits/old"): return {"tree": {"sha": "base-tree"}}
        if "/git/ref/heads/" in path: return {"object": {"sha": self.head}}
        return {"default_branch": "main"}
    def _put(self, path, body, *, method="PUT"):
        self.writes.append((path, body, method))
        return {"sha": "new-tree" if path.endswith("/trees") else "new-commit"}

def test_contract_update_uses_authorized_parent_and_fast_forward_cas():
    source = Source()
    assert source.write_contract("app", "targets: []", "feat: declare target", expected_revision="old") == "new-commit"
    tree, commit, update = source.writes
    assert tree[1]["base_tree"] == "base-tree"
    assert tree[1]["tree"][0]["path"] == "devops/promotion.yaml"
    assert tree[2] == commit[2] == "POST"
    assert commit[1]["parents"] == ["old"]
    assert update == ("/repos/org/app/git/refs/heads/main", {"sha": "new-commit", "force": False}, "PATCH")

def test_stale_head_has_no_write():
    source = Source("new")
    with pytest.raises(Conflict):
        source.write_contract("app", "targets: []", "feat: declare target", expected_revision="old")
    assert source.writes == []
