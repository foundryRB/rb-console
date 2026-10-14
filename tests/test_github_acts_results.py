"""Repository command acknowledgements cross the host boundary as semantic values."""

import pytest

from orchestrator.adapters.outbound.github.github_acts import GitHubActs
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.comment_created import CommentCreated
from orchestrator.domain.model.issue_closed import IssueClosed
from orchestrator.domain.model.pull_merge_result import PullMergeResult


@pytest.mark.parametrize("action,payload,expected", [
    ("merge", {"merged": True, "sha": "commit", "message": "Merged", "host_only": "discard"}, PullMergeResult(True, "commit", "Merged")),
    ("comment", {"id": 17, "html_url": "https://example/comment", "body": "discard"}, CommentCreated(17, "https://example/comment")),
    ("close_issue", {"number": 7, "state": "closed", "title": "discard"}, IssueClosed(7)),
    ("label", [{"name": "foundry-hidden", "color": "discard"}], None),
])
def test_host_acknowledgements_are_normalized(action, payload, expected):
    calls = []
    adapter = GitHubActs("org", lambda: "credential")
    adapter._req = lambda *args: calls.append(args) or payload
    args = ("org/app", 7, "body") if action in ("comment", "label") else ("org/app", 7)
    if action == "label":
        args = ("org/app", 7, "foundry-hidden")
    assert getattr(adapter, action)(*args) == expected
    assert len(calls) == 1


@pytest.mark.parametrize("action,payload", [("merge", {}), ("comment", {"id": True}), ("close_issue", {"number": 8, "state": "closed"}), ("label", [])])
def test_malformed_acknowledgement_is_unavailable_without_redispatch(action, payload):
    calls = []
    adapter = GitHubActs("org", lambda: "credential")
    adapter._req = lambda *args: calls.append(args) or payload
    args = ("org/app", 7, "body") if action in ("comment", "label") else ("org/app", 7)
    with pytest.raises(SourceUnavailable, match="acknowledgement"):
        getattr(adapter, action)(*args)
    assert len(calls) == 1
