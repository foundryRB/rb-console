import base64
import pytest
from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

class Transport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
    def json(self, url, token, **kwargs):
        self.calls.append(url)
        return self.responses[url.split("api.github.com", 1)[1]]

def test_pinned_scratch_file_performs_no_ref_discovery():
    transport = Transport({"/repos/org/app/contents/scope.md?ref=immutable": {"content": base64.b64encode(b"scope").decode()}})
    source = GitHubDeliverySource("org", lambda: "token", transport=transport)
    assert source.file('app', '.delivery/scope.md', revision='immutable').content == "scope"
    assert len(transport.calls) == 1

def test_tree_pins_default_and_scratch_independently():
    transport = Transport({"/repos/org/app/git/trees/default?recursive=1": {"tree": [{"path": "README.md", "type": "blob"}]}, "/repos/org/app/git/trees/scratch?recursive=1": {"tree": [{"path": "scope.md", "type": "blob"}]}})
    source = GitHubDeliverySource("org", lambda: "token", transport=transport)
    assert [row.path for row in source.tree("app", revision="default", scratch_revision="scratch")] == ["README.md", ".delivery", ".delivery/scope.md"]
    assert len(transport.calls) == 2

def test_default_revision_resolves_immutable_head():
    transport = Transport({"/repos/org/app": {"default_branch": "main"}, "/repos/org/app/git/ref/heads/main": {"object": {"sha": "immutable"}}})
    source = GitHubDeliverySource("org", lambda: "token", transport=transport)
    assert source.content_revision("app") == "immutable"

def test_truncated_tree_is_unavailable():
    transport = Transport({"/repos/org/app/git/trees/default?recursive=1": {"tree": [], "truncated": True}})
    source = GitHubDeliverySource("org", lambda: "token", transport=transport)
    with pytest.raises(SourceUnavailable):
        source.tree("app", revision="default")


def test_home_revision_uses_only_named_pair_credential():
    from orchestrator.adapters.outbound.github.github_door import GitHubDoor
    seen = []
    class PairTransport:
        def json(self, url, token, **kwargs):
            seen.append((url, token))
            return {"object": {"sha": "home-immutable"}}
    source = GitHubDoor(lambda name: "foreign-token" if name == "pair-key" else "", transport=PairTransport())
    assert source.repository_revision("foreign/app", "release", "pair-key") == "home-immutable"
    assert seen == [("https://api.github.com/repos/foreign/app/git/ref/heads/release", "foreign-token")]


@pytest.mark.parametrize("payload", [{}, [], {"tree": [{}]}, {"tree": [{"path": "app", "type": "unknown"}]}])
def test_malformed_tree_is_unavailable(payload):
    source = GitHubDeliverySource("org", lambda: "token", transport=Transport({"/repos/org/app/git/trees/default?recursive=1": payload}))
    with pytest.raises(SourceUnavailable, match="malformed"):
        source.tree("app", revision="default")
