"""The local delivery source scans a root and derives state from the scratch mount at
.delivery/; the GitHub source discovers by the line's delivery/* scratch ref and reads
the records from that ref's branch root - both feeding the same records-based derivation."""
import base64
import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import quote

import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle, lifecycle_digest
from orchestrator.adapters.outbound.github.github_delivery_source import GitHubDeliverySource
from orchestrator.adapters.outbound.filesystem.local_delivery_source import LocalDeliverySource
from orchestrator.domain.current_lifecycle import (
    CURRENT_LIFECYCLE,
    CURRENT_PLAYBOOK_REF,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

_REF = "delivery/2026-08-18"
_QREF = quote(_REF, safe="")


@intent('INT-FC-R164')
def test_malformed_local_configuration_is_unavailable(tmp_path):
    scratch = tmp_path / '.delivery'
    scratch.mkdir()
    (scratch / 'config.json').write_text('{broken', encoding='utf-8')
    source = LocalDeliverySource(tmp_path.parent)
    with pytest.raises(SourceUnavailable, match='configuration could not be read'):
        source.read_config(str(tmp_path))


@pytest.mark.parametrize("defect", ["digest", "revision"])
def test_scan_requires_a_valid_committed_lifecycle_pin(defect: str) -> None:
    payload = encode_lifecycle(CURRENT_LIFECYCLE)
    payload.update(digest=lifecycle_digest(CURRENT_LIFECYCLE), source_ref=CURRENT_PLAYBOOK_REF)
    if defect == "digest":
        payload["digest"] = "different"
    if defect == "revision":
        payload.pop("source_ref")

    def read(path: str, token: str):
        if path.startswith("/orgs/"):
            return [{"full_name": "org/app", "name": "app", "id": 1}]
        if "matching-refs/heads/delivery/" in path:
            return [{"ref": "refs/heads/delivery/line", "object": {"sha": "a" * 40}}]
        if "/contents?ref=" in path:
            return [{"name": "config.json", "sha": "b" * 40}]
        if "/git/blobs/" in path:
            return {"content": base64.b64encode(json.dumps({"lifecycle": payload}).encode()).decode()}
        raise AssertionError("A refused pin must stop further source work")

    source = GitHubDeliverySource("org", lambda: "token")
    source._get = read
    with pytest.raises(SourceUnavailable):
        source.scan()


@intent("INT-FC-R172")
@pytest.mark.parametrize("config", [None, {"mode": "one-shot"}])
def test_a_line_opened_without_the_console_is_observed_with_the_installed_definition(config) -> None:
    def read(path: str, token: str):
        if path.startswith("/orgs/"):
            return [{"full_name": "org/app", "name": "app", "id": 1}, {"full_name": "org/other", "name": "other", "id": 2}]
        if "matching-refs/heads/delivery/" in path:
            return [{"ref": "refs/heads/delivery/line", "object": {"sha": "a" * 40}}]
        if "/contents?ref=" in path:
            return [] if config is None else [{"name": "config.json", "sha": "b" * 40}]
        if "/git/blobs/" in path:
            return {"content": base64.b64encode(json.dumps(config).encode()).decode()}
        if "matching-refs/tags/" in path:
            return []
        raise AssertionError(path)

    source = GitHubDeliverySource("org", lambda: "token")
    source._get = read
    states = source.scan()
    assert sorted(state.repo for state in states) == ["org/app", "org/other"]
    assert all(state.lifecycle.phases == CURRENT_LIFECYCLE.phases for state in states)
    assert all(state.lifecycle.source_ref == "" for state in states)


@intent("INT-FC-R31")
def test_local_source_scans_only_delivery_repos(tmp_path):
    scratch = tmp_path / "acme" / ".delivery"
    scratch.mkdir(parents=True)
    (scratch / "README.md").write_text("scratch", encoding="utf-8")
    payload = encode_lifecycle(CURRENT_LIFECYCLE)
    payload["digest"] = lifecycle_digest(CURRENT_LIFECYCLE)
    payload["source_ref"] = CURRENT_PLAYBOOK_REF
    (scratch / "config.json").write_text(json.dumps({"lifecycle": payload}), encoding="utf-8")
    (tmp_path / "bare").mkdir()  # not a delivery: no .delivery/ mount

    states = LocalDeliverySource(tmp_path).scan()

    assert len(states) == 1
    assert states[0].exists is True
    assert states[0].status == "run-phase"
    assert states[0].repo.endswith("acme")

    # state_of resolves a single repo the same way, and a non-delivery reads as such
    src = LocalDeliverySource(tmp_path)
    assert src.state_of(str(tmp_path / "acme")).status == "run-phase"
    assert src.state_of(str(tmp_path / "bare")).status == "not-a-delivery"


@intent("INT-FC-R31")
def test_github_source_discovers_by_scratch_ref_not_topic():
    """GitHub discovery reads the contract's own fact: a repo is a delivery because it
    carries a live delivery/* scratch ref, never because of a repo topic. The per-repo
    probe is ONE matching-refs call - the org rescan's whole per-repo cost, with no
    second probe; a repo whose namespace is empty is not a delivery; the records are
    read from the resolved ref at branch root; and the org-wide topic search endpoint
    is never consulted."""
    org_repos = [  # neither carries any topic - discovery must not depend on one
        {"full_name": "example-org/acme", "name": "acme", "pushed_at": "t1", "topics": [], "archived": False},
        {"full_name": "example-org/bare", "name": "bare", "pushed_at": "t2", "topics": [], "archived": False},
    ]
    probes: list[str] = []

    def fake_get(path, token):
        assert "/search/repositories" not in path, "discovery must not use the topic search"
        if path.startswith("/orgs/example-org/repos"):
            return org_repos
        if path.endswith("/git/matching-refs/heads/delivery/"):
            probes.append(path)
            if path == "/repos/example-org/acme/git/matching-refs/heads/delivery/":
                return [{"ref": f"refs/heads/{_REF}", "object": {"sha": "tip0"}}]
            return []  # example-org/bare: an empty namespace, not a delivery
        if path == "/repos/example-org/acme/contents?ref=tip0":
            return [{"name": "proposal.md"}, {"name": "config.json"}]
        if path == "/repos/example-org/acme/contents/config.json?ref=tip0":
            payload = encode_lifecycle(CURRENT_LIFECYCLE)
            payload["digest"] = lifecycle_digest(CURRENT_LIFECYCLE)
            payload["source_ref"] = CURRENT_PLAYBOOK_REF
            return {"content": base64.b64encode(json.dumps({"lifecycle": payload}).encode()).decode()}
        if path == "/repos/example-org/acme/contents/proposal.md?ref=tip0":
            return {"content": base64.b64encode(b"proposal accepted 2026-07-09").decode()}
        if "/git/matching-refs/tags/" in path:
            return []
        raise RuntimeError(f"404 {path}")

    src = GitHubDeliverySource("example-org", lambda: "tok")
    src._get = fake_get

    states = {s.repo: s for s in src.scan()}

    assert "example-org/acme" in states and states["example-org/acme"].exists is True
    assert states["example-org/acme"].status != "not-a-delivery"
    assert states["example-org/acme"].scratch_ref == _REF  # the resolved ref rides the state
    assert "example-org/bare" not in states  # no delivery/* ref -> not a delivery, whatever its topics
    assert len(probes) == 2  # one matching-refs probe per org repo, nothing more


@intent("INT-FC-R31")
def test_more_than_one_scratch_ref_surfaces_as_an_anomaly_never_a_silent_pick():
    """Exactly one delivery/* ref may exist (decision 0003). Two of them is an anomaly
    the fleet must SEE - a degraded state naming both refs - never a coin-flip read of
    whichever ref the API listed first."""
    def fake_get(path, token):
        if path.startswith("/orgs/example-org/repos"):
            return [{"full_name": "example-org/twins", "name": "twins", "pushed_at": "t1", "topics": []}]
        if path == "/repos/example-org/twins/git/matching-refs/heads/delivery/":
            return [
                {"ref": "refs/heads/delivery/2026-08-01", "object": {"sha": "a"}},
                {"ref": "refs/heads/delivery/2026-08-18", "object": {"sha": "b"}},
            ]
        raise AssertionError(f"an anomalous repo must not be read further: {path}")

    src = GitHubDeliverySource("example-org", lambda: "tok")
    src._get = fake_get

    for state in (src.scan()[0], src.state_of("example-org/twins")):
        assert state.status == "degraded"
        assert "delivery/2026-08-01" in (state.next_command or "")
        assert "delivery/2026-08-18" in (state.next_command or "")


@intent("INT-FC-R31")
def test_file_reads_serve_the_working_checkout_view(tmp_path):
    """The file read serves the same view a working checkout shows on disk: a path under
    .delivery/ is the scratch mount and resolves against the line's ref at branch root
    (no .delivery/ prefix on the ref); every other path reads the default branch. The
    local source agrees for free, because its disk layout IS the mount."""
    def fake_get(path, token):
        if path == "/repos/example-org/acme/git/matching-refs/heads/delivery/":
            return [{"ref": f"refs/heads/{_REF}", "object": {"sha": "tip0"}}]
        if path == "/repos/example-org/acme/contents/proposal.md?ref=tip0":
            return {"content": base64.b64encode(b"the proposal").decode(), "size": 12}
        if path == "/repos/example-org/acme":
            return {"id": 42, "default_branch": "main"}
        if path == "/repos/example-org/acme/git/ref/heads/main":
            return {"object": {"sha": "main0"}}
        if path == "/repos/example-org/acme/contents/src/app.py?ref=main0":
            return {"content": base64.b64encode(b"print('app')").decode(), "size": 12}
        raise RuntimeError(f"404 {path}")

    src = GitHubDeliverySource("example-org", lambda: "tok")
    src._get = fake_get

    assert src.file('example-org/acme', '.delivery/proposal.md').content == "the proposal"
    assert src.file('example-org/acme', 'src/app.py').content == "print('app')"

    # And the local source: the mount path reads straight off disk.
    repo = tmp_path / "acme"
    (repo / ".delivery").mkdir(parents=True)
    (repo / ".delivery" / "proposal.md").write_text("the proposal", encoding="utf-8")
    assert LocalDeliverySource(tmp_path).file(str(repo), '.delivery/proposal.md').content == "the proposal"
@intent("INT-FC-R01")
def test_a_repo_with_no_scratch_ref_reads_not_a_delivery_remotely():
    """The remote half of the claim: an empty delivery/* namespace IS the no-live-scratch
    fact, so the source resolves the repo to not-a-delivery without reading anything
    else (the local half is the missing .delivery/ mount, pinned above)."""
    def fake_get(path, token):
        if path == "/repos/example-org/bare/git/matching-refs/heads/delivery/":
            return []
        raise AssertionError(f"a bare repo must not be read past the probe: {path}")

    src = GitHubDeliverySource("example-org", lambda: "tok")
    src._get = fake_get
    state = src.state_of("example-org/bare")
    assert state.status == "not-a-delivery"
    assert state.exists is False and state.scratch_ref == ""


@intent("INT-FC-R01")
def test_an_empty_repository_is_not_a_delivery_and_never_fails_the_scan():
    """GitHub answers a repository with no commits with 409 "Git Repository is empty."
    on the matching-refs probe: its definite answer that the repo carries no ref at all,
    so not-a-delivery, never an unreadable repo that holds the whole fleet's scan. Any
    other 409 is still a fault (INT-FC-R144)."""
    org_repos = [
        {"full_name": "example-org/acme", "name": "acme", "pushed_at": "t1", "topics": [], "archived": False},
        {"full_name": "example-org/empty", "name": "empty", "pushed_at": "t2", "topics": [], "archived": False},
    ]
    answer = {"message": "Git Repository is empty."}

    def fake_get(path, token):
        if path.startswith("/orgs/example-org/repos"):
            return org_repos
        if path == "/repos/example-org/empty/git/matching-refs/heads/delivery/":
            raise HTTPError(path, 409, "Conflict", {}, BytesIO(json.dumps(answer).encode()))
        if path == "/repos/example-org/acme/git/matching-refs/heads/delivery/":
            return [{"ref": f"refs/heads/{_REF}", "object": {"sha": "tip9"}}]
        if path == "/repos/example-org/acme/contents?ref=tip9":
            return [{"name": "proposal.md"}]
        if path == "/repos/example-org/acme/contents/proposal.md?ref=tip9":
            return {"content": base64.b64encode(b"proposal accepted 2026-07-09").decode()}
        if "/git/matching-refs/tags/" in path:
            return []
        raise AssertionError(f"unexpected read: {path}")

    src = GitHubDeliverySource("example-org", lambda: "tok")
    src._get = fake_get
    states = {s.repo: s for s in src.scan()}
    assert list(states) == ["example-org/acme"] and states["example-org/acme"].revision == "tip9"
    assert src.state_of("example-org/empty").status == "not-a-delivery"

    answer = {"message": "Conflict"}
    with pytest.raises(SourceUnavailable):
        src.scan()


@intent("INT-FC-R39")
def test_the_config_and_record_reads_follow_the_line_ref():
    """read_config and present_records ride the resolved ref: the config comes off the
    line's branch (branch-root config.json, ?ref= qualified), and the record listing is
    the ref's root listing - never an unqualified default-branch read."""
    def fake_get(path, token):
        if path == "/repos/example-org/acme/git/matching-refs/heads/delivery/":
            return [{"ref": f"refs/heads/{_REF}", "object": {"sha": "tip0"}}]
        if path == f"/repos/example-org/acme/contents/config.json?ref={_QREF}":
            return {"content": base64.b64encode(b'{"mode": "one-shot"}').decode()}
        if path == f"/repos/example-org/acme/contents?ref={_QREF}":
            return [{"name": "proposal.md"}, {"name": "journal.md"}, {"name": "README.md"}]
        raise AssertionError(f"an unqualified scratch read: {path}")

    src = GitHubDeliverySource("example-org", lambda: "tok")
    src._get = fake_get
    assert src.read_config("example-org/acme") == {"mode": "one-shot"}
    assert src.present_records("example-org/acme") == ["proposal.md"]


@intent("INT-FC-R144")
def test_an_unreadable_org_raises_rather_than_reading_as_an_empty_one():
    """The distinction the whole hold rests on. This list is what the Fleet cache is
    REPLACED from, so [] here is published as 'this Foundry has no projects'. A read that
    could not be MADE must say so instead - otherwise one timeout speaks for the floor."""
    src = GitHubDeliverySource("example-org", lambda: "ghp_x")

    def boom(path, token):
        raise OSError("timed out")

    src._get = boom
    with pytest.raises(SourceUnavailable):
        src.list_org_repos()
    with pytest.raises(SourceUnavailable):
        src.scan()


@intent("INT-FC-R144")
def test_a_missing_credential_raises_too_rather_than_reading_as_an_empty_org():
    # An unconfigured console and an unreachable one are the same fact for this read: we
    # cannot ask. Answering [] is what let the empty state blame a token for a scan that
    # never ran - including when the token was fine and its READ was what failed.
    src = GitHubDeliverySource("example-org", lambda: "")
    with pytest.raises(SourceUnavailable):
        src.list_org_repos()
    with pytest.raises(SourceUnavailable):
        src.scan()


@intent("INT-FC-R144")
def test_an_org_that_answers_with_no_repos_is_still_empty():
    # Raising must not cost us the ability to say 'empty' when that is the truth.
    src = GitHubDeliverySource("example-org", lambda: "ghp_x")
    src._get = lambda path, token: []
    assert src.list_org_repos() == []
    assert src.scan() == []
