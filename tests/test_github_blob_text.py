"""GitHub folded base64 remains strict about alphabet and decoded UTF-8."""
import base64
import json

import pytest

from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle, lifecycle_digest
from orchestrator.adapters.outbound.github.blob_text import blob_text
from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource
from orchestrator.adapters.outbound.github.github_promotion_source import GithubPromotionSource
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE, CURRENT_PLAYBOOK_REF
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


def folded(text):
    encoded = base64.b64encode(text.encode()).decode()
    return {"content": "\n".join(encoded[index:index+60] for index in range(0, len(encoded), 60)) + "\n", "sha": "blob-sha"}


@pytest.mark.parametrize("separator", ["\n", "\r\n", " \t\v\f"])
def test_ascii_folding_decodes_complete_file(separator):
    text = "# A file\n" + "a longer UTF-8 line: caf\u00e9\n" * 5
    encoded = base64.b64encode(text.encode()).decode()
    blob = {"content": separator.join(encoded[index:index+4] for index in range(0, len(encoded), 4))}
    assert blob_text(blob) == text


@pytest.mark.parametrize("content", ["!!!!\n", "YQ==!\n", "//8=\n", "YQ==\u00a0", "YQ=\n", None])
def test_corrupt_alphabet_non_ascii_whitespace_and_non_utf8_fail(content):
    with pytest.raises(SourceUnavailable): blob_text({"content": content})


def test_delivery_file_and_config_accept_folded_content(monkeypatch):
    source = GitHubDeliverySource("org", lambda: "token")
    monkeypatch.setattr(source, "_get", lambda *args: folded("caf\u00e9\n"))
    assert source.file('app', '.delivery/proposal.md', revision='a' * 40).content == "caf\u00e9\n"
    monkeypatch.setattr(source, "_get", lambda *args: folded(json.dumps({"mode": "interactive"})))
    assert source.read_config("app", revision="a"*40) == {"mode": "interactive"}


def test_lifecycle_pin_accepts_folded_content(monkeypatch):
    source = GitHubDeliverySource("org", lambda: "token")
    payload = encode_lifecycle(CURRENT_LIFECYCLE)
    payload.update(digest=lifecycle_digest(CURRENT_LIFECYCLE), source_ref=CURRENT_PLAYBOOK_REF)
    monkeypatch.setattr(source, "_get", lambda *args: folded(json.dumps({"lifecycle": payload})))
    definition = source._definition_of("org/app", [{"name": "config.json", "sha": "blob"}], "token", "a"*40)
    assert definition.source_ref == CURRENT_PLAYBOOK_REF
    assert lifecycle_digest(definition) == lifecycle_digest(CURRENT_LIFECYCLE)


def test_promotion_contract_accepts_folded_content(monkeypatch):
    source = GithubPromotionSource("org", lambda: "token")
    monkeypatch.setattr(source, "_get", lambda *args: folded("targets: []\n"))
    assert source.contract_text("app", revision="a"*40) == "targets: []\n"


def test_gitignore_folded_content_preserves_existing_file(monkeypatch):
    store = GitHubRepoStore("org", lambda: "token")
    calls = []
    def request(method, path, *args):
        calls.append(method)
        return folded("# Ignore temporary files\n.delivery/\n")
    monkeypatch.setattr(store, "_req", request)
    store._ensure_scratch_ignored("org/app", "token")
    assert calls == ["GET"]
