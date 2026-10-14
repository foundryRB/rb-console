"""Save-time validation of a git identity's PAT (INT-FC-R142): the token is exercised against
the repo host before it is seated, fail-closed on an explicit 401/403 or on a token belonging
to somebody other than the declared login, fail-open on a transport failure, a timeout, or no
check wired. The git twin of test_credential_validation.py. Audit: csd-intent ."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
import io
import json
import urllib.error
import urllib.request
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.adapters.outbound.github.github_acts import GitHubActs
from capability_support import make_capabilities

class FakeRepos:

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        return target

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class FakeCheck:
    """A GitCredentialCheck stub answering a fixed verdict, recording what it was asked."""

    def __init__(self, verdict, detail='stubbed'):
        self._verdict = verdict
        self._detail = detail
        self.checked = None

    def validate_identity(self, token, login=''):
        self.checked = (token, login)
        return (self._verdict, self._detail)

def _svc(check):
    return make_capabilities(FakeRepos(), config=InMemoryConfigStore(), gitcheck=check)

@intent('INT-FC-R142')
def test_a_valid_pat_passes_the_preflight_and_is_seated():
    check = FakeCheck(verdict=True)
    svc = _svc(check)
    saved = svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'ghp-good', **command_kwargs(''))
    assert saved['configured'] is True
    assert check.checked == ('ghp-good', 'foundry-delivery-bot')

@intent('INT-FC-R142')
def test_an_explicit_refusal_rejects_the_save_and_never_seats_the_token():
    svc = _svc(FakeCheck(verdict=False, detail='GitHub rejected the token (401)'))
    with pytest.raises(ValueError) as exc:
        svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'ghp-revoked', **command_kwargs(''))
    assert '401' in str(exc.value)
    assert svc.list_git_identities.execute() == []

@intent('INT-FC-R142')
def test_a_transport_failure_fails_open_and_the_token_is_still_seated():
    svc = _svc(FakeCheck(verdict=None, detail='GitHub unreachable'))
    saved = svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'ghp-good', **command_kwargs(''))
    assert saved['configured'] is True

@intent('INT-FC-R142')
def test_no_check_wired_fails_open_rather_than_blocking_every_save():
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore())
    saved = svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'ghp-good', **command_kwargs(''))
    assert saved['configured'] is True

@intent('INT-FC-R142')
def test_an_edit_carrying_no_token_never_calls_the_host():
    check = FakeCheck(verdict=False)
    svc = _svc(check)
    svc.set_git_identity.execute('Foundry Delivery', 'new@x', 'foundry-delivery-bot', None, **command_kwargs(''))
    assert check.checked is None

class _Resp:
    headers = {}
    status = 200

    def __init__(self, body, headers=None):
        self._body = json.dumps(body).encode()
        self.headers = headers or {}

    def read(self, *_size):
        body, self._body = self._body, b''
        return body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

@intent('INT-FC-R142')
def test_the_adapter_folds_the_hosts_answer_into_a_verdict(monkeypatch):
    from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
    acts = GitHubActs('example-org', lambda: 'console-tok', transport=GitHubTransport(opener=lambda request, timeout: urllib.request.build_opener().open(request, timeout=timeout)))
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: (lambda *a, **k: _Resp({'login': 'foundry-delivery-bot'}))(request, timeout=timeout))
    verdict, detail = acts.validate_identity('ghp-good', 'foundry-delivery-bot')
    assert verdict is True and 'foundry-delivery-bot' in detail
    assert acts.validate_identity('ghp-good', 'Foundry-Delivery-Bot')[0] is True
    verdict, detail = acts.validate_identity('ghp-good', 'foundry-review-bot')
    assert verdict is False
    assert 'foundry-delivery-bot' in detail and 'foundry-review-bot' in detail
    assert acts.validate_identity('ghp-good')[0] is True

    def _http_error(code):

        def _raise(*a, **k):
            raise urllib.error.HTTPError('u', code, 'no', {}, io.BytesIO(b'{}'))
        return _raise
    for code in (401, 403):
        monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: _http_error(code)(request, timeout=timeout))
        assert acts.validate_identity('ghp-revoked', 'foundry-delivery-bot')[0] is False
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: _http_error(503)(request, timeout=timeout))
    assert acts.validate_identity('ghp-good', 'foundry-delivery-bot')[0] is None

    def _unreachable(*a, **k):
        raise urllib.error.URLError('getaddrinfo failed')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: _unreachable(request, timeout=timeout))
    assert acts.validate_identity('ghp-good', 'foundry-delivery-bot')[0] is None

    def _timeout(*a, **k):
        raise TimeoutError('timed out')
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: _timeout(request, timeout=timeout))
    assert acts.validate_identity('ghp-good', 'foundry-delivery-bot')[0] is None
    assert acts.validate_identity('', 'foundry-delivery-bot')[0] is False

@intent('INT-FC-R142')
def test_an_expiring_pat_says_so_in_the_detail(monkeypatch):
    from orchestrator.adapters.outbound.github.github_transport import GitHubTransport
    acts = GitHubActs('example-org', lambda: 'console-tok', transport=GitHubTransport(opener=lambda request, timeout: urllib.request.build_opener().open(request, timeout=timeout)))
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda self, request, timeout=0: (lambda *a, **k: _Resp({'login': 'foundry-delivery-bot'}, {'github-authentication-token-expiration': '2026-09-30 12:00:00 UTC'}))(request, timeout=timeout))
    verdict, detail = acts.validate_identity('ghp-good', 'foundry-delivery-bot')
    assert verdict is True and '2026-09-30' in detail
