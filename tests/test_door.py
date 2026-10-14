from maintenance_fixtures import semantic_comment, semantic_pr
from maintenance_fixtures import semantic_pr
"""The door to a customer's repository (foundry-platform#167, ADR-044 section 6).

Three things are held here, and they are the three the carve exists to make true.

The IMPLEMENTATION reads GitHub and degrades rather than raising, keeping the one
distinction every promotion surface depends on: a pair we could not see is not a pair
that has accepted nothing.

The SELECTOR picks the implementation per app from the host that app's credential
reaches, and a host this Foundry has no implementation for degrades exactly as an unheld
credential does - never raising, because a missing implementation is not an outage.

The VOCABULARY (what a ``promote/`` branch means, what a marked comment points at) is the
line's, not the host's, so a second door inherits every rule of it unchanged.

Audit: csd-intent .
"""
import json
import urllib.request
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.repositories.host_selected_door import HostSelectedDoor
from orchestrator.adapters.outbound.github.github_door import GitHubDoor
from orchestrator.domain.services.repository_door import accepted_release, home_pr_from_comments, open_door_ref
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

class FakeResponse:
    headers = {}
    status = 200

    def __init__(self, payload):
        self._payload = json.dumps(payload).encode('utf-8')
        self.status = 200
        self.headers = {}

    def read(self, *_args):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

def _patched(monkeypatch, routes: dict):
    """Serve the recorded routes; anything else raises, as an unreachable host would.

    Longest fragment wins, because a PR's own path is a prefix of its reviews' path
    (``/pulls/14`` and ``/pulls/14/reviews``) and route order should not decide which
    read a case is asserting about."""
    seen: list[tuple[str, str]] = []

    def fake_urlopen(request, timeout=0):
        url = request.full_url if hasattr(request, 'full_url') else str(request)
        seen.append((url, request.headers.get('Authorization', '')))
        matches = [f for f in routes if f in url]
        if matches:
            return FakeResponse(routes[max(matches, key=len)])
        raise OSError('unreachable')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: fake_urlopen(request, timeout=timeout))
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: fake_urlopen(request, timeout))
    return seen

def _door(secrets=None):
    held = secrets if secrets is not None else {'partner-pair': 'their-grant'}
    return GitHubDoor(lambda name: held.get(name, ''))

@intent('INT-FC-R127')
def test_a_pair_read_never_falls_back_to_the_consoles_own_token() -> None:
    """Our token reaches OUR org and was never granted to theirs. A pair read that fell
    back to it would answer for a door the platform cannot open - the exact reason a
    target with an unusable credential rendered identically to a working one.

    The adapter holds this structurally now (#167): it is handed the PAIR resolver and
    nothing else, so there is no console token here to fall back TO."""
    held = {'partner-pair': 'pat-PAIR'}
    door = GitHubDoor(lambda name: held.get(name, ''))
    used: list[str] = []
    door._get = lambda path, credential: used.append(held.get(credential, ''))
    door.open_pull_requests('their-org/their-repo', 'main', 'partner-pair')
    assert used == ['pat-PAIR']
    used.clear()
    door.open_pull_requests('their-org/their-repo', 'main', 'unregistered')
    assert used == ['']
    assert not hasattr(door, '_token_provider')

class TestTheCredentialIsTheirsOrNothing:
    """The invariant the whole adapter exists to hold."""

    def test_an_unheld_credential_attempts_no_read_at_all(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {})
        door = _door(secrets={})
        with pytest.raises(SourceUnavailable):
            door.pull_request('their-org/repo', 14, 'partner-pair')
        with pytest.raises(SourceUnavailable):
            door.open_pull_requests('their-org/repo', 'main', 'partner-pair')
        with pytest.raises(SourceUnavailable):
            door.closed_pull_requests('their-org/repo', 'main', 'partner-pair')
        assert seen == []

    def test_an_unnamed_credential_attempts_no_read_either(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {})
        with pytest.raises(SourceUnavailable):
            _door().pull_request('their-org/repo', 14, '')
        assert seen == []

    def test_every_read_rides_the_pairs_own_grant(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {'/pulls/14': {'number': 14, 'head': {'sha': 'abc'}}, '/pulls/14/reviews': [], 'check-runs': {'check_runs': []}})
        _door().pull_request('their-org/repo', 14, 'partner-pair')
        assert seen and all((auth == 'Bearer their-grant' for _, auth in seen))

    def test_an_unreachable_host_degrades_rather_than_raising(self, monkeypatch) -> None:
        _patched(monkeypatch, {})
        door = _door()
        with pytest.raises(SourceUnavailable):
            door.pull_request('their-org/repo', 14, 'partner-pair')
        with pytest.raises(SourceUnavailable):
            door.open_pull_requests('their-org/repo', 'main', 'partner-pair')
        with pytest.raises(SourceUnavailable):
            door.closed_pull_requests('their-org/repo', 'main', 'partner-pair')

class TestOnePullRequest:

    def test_the_three_reads_a_position_needs_arrive_as_one(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {'/pulls/14': {'number': 14, 'state': 'open', 'head': {'sha': 'abc'}}, '/pulls/14/reviews': [{'state': 'APPROVED'}], 'check-runs': {'check_runs': [{'conclusion': 'success'}]}})
        pr = _door().pull_request('their-org/repo', 14, 'partner-pair')
        assert [review.state for review in pr.reviews] == ['APPROVED']
        assert [check.conclusion for check in pr.checks] == ['success']
        assert not any(('state=open' in url for url, _ in seen))

    def test_a_pr_that_could_not_be_read_asks_nothing_further(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {'/pulls/14/reviews': [{'state': 'APPROVED'}]})
        with pytest.raises(SourceUnavailable):
            _door().pull_request('their-org/repo', 14, 'partner-pair')
        assert len(seen) == 3
        assert {url for url, _ in seen} == {'https://api.github.com/repos/their-org/repo/pulls/14'}

    def test_a_head_with_no_sha_skips_the_checks_read(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {'/pulls/14': {'number': 14}, '/pulls/14/reviews': []})
        pr = _door().pull_request('their-org/repo', 14, 'partner-pair')
        assert pr.checks == ()
        assert not any(('check-runs' in url for url, _ in seen))

class TestListings:

    def test_the_pairs_repo_is_read_as_given_never_prefixed_with_ours(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {'state=open': []})
        _door().open_pull_requests('their-org/repo', 'main', 'partner-pair')
        assert '/repos/their-org/repo/pulls' in seen[0][0]

    def test_a_readable_repo_with_nothing_open_is_empty_not_unreadable(self, monkeypatch) -> None:
        _patched(monkeypatch, {'state=open': []})
        assert _door().open_pull_requests('their-org/repo', 'main', 'partner-pair') == ()

    def test_closed_listings_carry_the_merge_fact(self, monkeypatch) -> None:
        _patched(monkeypatch, {'state=closed': [{'number': 14, 'merged_at': '2026-08-01', 'head': {'ref': 'promote/v1.38.0'}}]})
        prs = _door().closed_pull_requests('their-org/repo', 'main', 'partner-pair')
        assert prs and prs[0].merged

class TestTheSelector:
    """Selected per app: the contract names the credential, the registration names the
    host, the host names the implementation."""

    class Recorder:

        def __init__(self, tag):
            self.tag = tag

        def pull_request(self, repo, number, credential):
            return semantic_pr({'title': self.tag})

        def open_pull_requests(self, repo, base, credential):
            return tuple(semantic_pr(record) for record in ([{'title': self.tag}]))

        def closed_pull_requests(self, repo, base, credential):
            return tuple(semantic_pr(record) for record in ([{'title': self.tag}]))

    def test_the_credentials_host_chooses_the_implementation(self) -> None:
        hosts = {'partner-pair': 'github.com', 'other-pair': 'dev.azure.com'}
        door = HostSelectedDoor({'github.com': self.Recorder('gh'), 'dev.azure.com': self.Recorder('ado')}, lambda name: hosts.get(name, ''))
        assert door.pull_request('a/b', 1, 'partner-pair') .title == 'gh'
        assert door.pull_request('c/d', 2, 'other-pair') .title == 'ado'

    def test_a_registration_carrying_no_host_reads_as_github(self) -> None:
        door = HostSelectedDoor({'github.com': self.Recorder('gh')}, lambda name: '')
        assert door.pull_request('a/b', 1, 'partner-pair') .title == 'gh'

    def test_a_host_with_no_implementation_degrades_and_never_raises(self) -> None:
        door = HostSelectedDoor({'github.com': self.Recorder('gh')}, lambda name: 'bitbucket.example')
        assert door.pull_request('a/b', 1, 'partner-pair') is None
        assert door.open_pull_requests('a/b', 'main', 'partner-pair') is None
        assert door.closed_pull_requests('a/b', 'main', 'partner-pair') is None

class TestTheDoorsVocabulary:
    """What a ``promote/`` branch means belongs to the promotion line, not to GitHub:
    a second implementation inherits every rule below without restating one."""

    def test_an_open_promote_branch_is_the_door_in_flight(self) -> None:
        assert open_door_ref(tuple(semantic_pr(record) for record in ([{'number': 14, 'head': {'ref': 'promote/1.42.0'}}]))) == 'PR 14'

    def test_an_unrelated_open_pull_request_is_not_a_door(self) -> None:
        assert open_door_ref(tuple(semantic_pr(record) for record in ([{'number': 9, 'head': {'ref': 'feature/theirs'}}]))) == ''

    def test_an_unreadable_listing_shows_no_open_door(self) -> None:
        assert open_door_ref(None) == ''

    def test_the_merged_door_carries_the_accepted_release(self) -> None:
        assert accepted_release(tuple(semantic_pr(record) for record in ([{'number': 20, 'merged_at': None, 'head': {'ref': 'promote/1.40.0'}}, {'number': 14, 'merged_at': '2026-08-01', 'head': {'ref': 'promote/v1.38.0'}}]))) == '1.38.0'

    def test_a_pair_that_merged_nothing_reads_as_empty_not_unreadable(self) -> None:
        assert accepted_release(tuple(semantic_pr(record) for record in ([]))) == ''

    def test_a_pair_we_could_not_read_is_unreadable_not_empty(self) -> None:
        assert accepted_release(None) is None

    def test_a_merged_branch_of_theirs_is_not_an_accepted_release(self) -> None:
        assert accepted_release(tuple(semantic_pr(record) for record in ([{'merged_at': '2026-08-01', 'head': {'ref': 'hotfix/theirs'}}]))) == ''

class TestTheHomePrPointer:
    """The marker is written on OUR ticket and points at THEIR host, so its shape is the
    door's (it moved here from the resolver with the carve)."""

    def test_the_pointer_is_read_back_off_the_marked_comment(self) -> None:
        body = '<!-- foundry:home-pr https://github.com/acme/portal/pull/14 -->\n\nResolved.'
        assert home_pr_from_comments(tuple(semantic_comment(record) for record in ([{'body': body}]))) == ('acme/portal', 14)

    def test_the_host_in_the_pointer_is_free(self) -> None:
        body = '<!-- foundry:home-pr https://git.acme.example/acme/portal/pull/7 -->'
        assert home_pr_from_comments(tuple(semantic_comment(record) for record in ([{'body': body}]))) == ('acme/portal', 7)

    def test_the_latest_marked_comment_wins(self) -> None:
        first = '<!-- foundry:home-pr https://github.com/acme/portal/pull/14 -->'
        second = '<!-- foundry:home-pr https://github.com/acme/portal/pull/21 -->'
        assert home_pr_from_comments(tuple(semantic_comment(record) for record in ([{'body': first}, {'body': second}]))) == ('acme/portal', 21)

    def test_no_marker_is_no_pointer(self) -> None:
        assert home_pr_from_comments(tuple(semantic_comment(record) for record in ([{'body': 'just a comment'}]))) is None
        assert home_pr_from_comments(tuple(semantic_comment(record) for record in ([]))) is None
