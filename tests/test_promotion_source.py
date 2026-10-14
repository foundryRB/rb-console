"""The promotion source's INSTALL-SIDE reads: every one degrades rather than guessing.

A pair's own repository is not read here any more - that is the Door's (#167), and its
suite is ``test_door.py``. What stays is the contract, the deploy branches, and the
acceptance signals, all on the console's own credential."""
import json
import urllib.request
import pytest
from orchestrator.adapters.outbound.github.github_promotion_source import CONTRACT_PATH, GithubPromotionSource
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
    """Serve the recorded routes; anything else raises, as an unreachable host would."""
    seen: list[str] = []

    def fake_urlopen(request, timeout=0):
        url = request.full_url if hasattr(request, 'full_url') else str(request)
        seen.append(url)
        for fragment, payload in routes.items():
            if fragment in url:
                return FakeResponse(payload)
        raise OSError('unreachable')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: fake_urlopen(request, timeout=timeout))
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: fake_urlopen(request, timeout))
    return seen

def _source(token='t'):
    return GithubPromotionSource('Test-Org', lambda: token)

class TestDegradation:

    def test_without_a_credential_every_read_degrades(self, monkeypatch) -> None:
        seen = _patched(monkeypatch, {})
        source = _source(token='')
        with pytest.raises(SourceUnavailable):
            source.contract_text('app')
        with pytest.raises(SourceUnavailable):
            source.environment_values('app', 'example', 'prod')
        assert seen == []

    def test_an_unreachable_host_degrades_rather_than_raising(self, monkeypatch) -> None:
        _patched(monkeypatch, {})
        source = _source()
        with pytest.raises(SourceUnavailable):
            source.contract_text('app')
        with pytest.raises(SourceUnavailable):
            source.environment_values('app', 'example', 'prod')

class TestContractAndValues:

    def test_the_contract_is_read_off_the_default_branch(self, monkeypatch) -> None:
        import base64
        body = base64.b64encode(b'targets: []\n').decode()
        seen = _patched(monkeypatch, {CONTRACT_PATH: {'content': body}})
        assert _source().contract_text('app') == 'targets: []\n'
        assert '?ref=' not in seen[0]

    def test_environment_values_are_read_off_that_installs_deploy_branch(self, monkeypatch) -> None:
        import base64
        body = base64.b64encode(b'app:\n  image:\n    tag: 1.2.3\n').decode()
        seen = _patched(monkeypatch, {'prod/values.yaml': {'content': body}})
        assert 'tag: 1.2.3' in (_source().environment_values('app', 'example', 'prod') or '')
        assert 'ref=deploy-example' in seen[0]

class TestSuiteVerdict:
    """A suite is read where it publishes, and a healthy 200 is not a pass."""

    @staticmethod
    def _serving(monkeypatch, *, status: int, body: str):

        class Response:
            headers = {}
            status = 200

            def __init__(self):
                self.status = status

            def read(self, *_a):
                return body.encode('utf-8')

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        monkeypatch.setattr(urllib.request, 'urlopen', lambda request, timeout=0: Response())

    def test_the_declared_match_is_what_says_passing(self, monkeypatch) -> None:
        self._serving(monkeypatch, status=200, body='{"result":"passed","n":42}')
        assert _source().read_suite('https://ci/api', '"result":"passed"') is True

    def test_a_failure_published_as_a_healthy_200_is_never_green(self, monkeypatch) -> None:
        self._serving(monkeypatch, status=200, body='{"result":"failed","n":42}')
        assert _source().read_suite('https://ci/api', '"result":"passed"') is None

    def test_an_answer_without_the_match_is_unreadable_not_a_live_no(self, monkeypatch) -> None:
        self._serving(monkeypatch, status=200, body='<html>some other service</html>')
        assert _source().read_suite('https://ci/api', '"result":"passed"') is None

    def test_no_match_declared_makes_answering_the_verdict(self, monkeypatch) -> None:
        self._serving(monkeypatch, status=200, body='anything at all')
        assert _source().read_suite('https://ci/api') is True

    def test_a_non_2xx_is_unreadable_rather_than_failing(self, monkeypatch) -> None:
        self._serving(monkeypatch, status=503, body='')
        assert _source().read_suite('https://ci/api', '"result":"passed"') is None

    def test_an_unreachable_endpoint_is_unreadable(self, monkeypatch) -> None:

        def refuse(*_a, **_k):
            raise OSError('no route to host')
        monkeypatch.setattr(urllib.request, 'urlopen', refuse)
        assert _source().read_suite('https://ci/api', 'x') is None

    def test_no_coordinate_asks_nothing(self, monkeypatch) -> None:

        def explode(*_a, **_k):
            raise AssertionError('a suite with no coordinate must not be asked')
        monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: explode(request, timeout=timeout))
        assert _source().read_suite('') is None
