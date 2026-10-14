"""Selection-time credential validation (issue #30): a credential is exercised against the
resolved endpoint before it is seated, fail-closed on an explicit 401/403 answer and
fail-open on a transport failure, a timeout, or no driver wired. Audit: csd-intent ."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
import subprocess
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.adapters.outbound.agents.http_driver_agent import HttpDriverAgent
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

class FakeCreds:

    def __init__(self):
        self.store = {}

    def put_delivery(self, slug, credential):
        self.store[slug] = credential

    def has_delivery(self, slug):
        return slug in self.store

    def get_delivery(self, slug):
        return self.store.get(slug, '')

    def delivery_ref(self, slug):
        return f'fc-delivery-{slug}'

class FakeDriver:
    """A driver stub whose validate() answers a fixed verdict (True/False/None) and
    records the credential/model/base_url it was asked to check."""

    def __init__(self, verdict):
        self._verdict = verdict
        self.checked = None

    def chat(self, system, messages, *, credential, model='', base_url='', max_tokens=1024):
        return 'ok'

    def validate(self, credential, model='', base_url=''):
        self.checked = (credential, model, base_url)
        return self._verdict

@intent('INT-FC-R114')
def test_a_valid_credential_passes_the_preflight_and_is_seated():
    creds = FakeCreds()
    driver = FakeDriver(verdict=True)
    svc = make_capabilities(FakeRepos(), credentials=creds, config=InMemoryConfigStore(), driver=driver)
    cfg = svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'haiku', 'oat-tok', **command_kwargs('example-org/acme'))
    assert cfg['credentialed'] is True
    assert creds.store['acme'] == 'oat-tok'
    assert driver.checked == ('oat-tok', 'haiku', '')

@intent('INT-FC-R114')
def test_an_explicit_401_rejects_the_save_and_never_seats_the_credential():
    creds = FakeCreds()
    driver = FakeDriver(verdict=False)
    svc = make_capabilities(FakeRepos(), credentials=creds, config=InMemoryConfigStore(), driver=driver)
    with pytest.raises(ValueError):
        svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'haiku', 'bad-tok', **command_kwargs('example-org/acme'))
    assert creds.store == {}

@intent('INT-FC-R114')
def test_a_transport_failure_fails_open_and_the_credential_is_still_seated():
    creds = FakeCreds()
    driver = FakeDriver(verdict=None)
    svc = make_capabilities(FakeRepos(), credentials=creds, config=InMemoryConfigStore(), driver=driver)
    cfg = svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'haiku', 'oat-tok', **command_kwargs('example-org/acme'))
    assert cfg['credentialed'] is True
    assert creds.store['acme'] == 'oat-tok'

@intent('INT-FC-R114')
def test_no_driver_wired_fails_open_rather_than_blocking_every_save():
    creds = FakeCreds()
    svc = make_capabilities(FakeRepos(), credentials=creds, config=InMemoryConfigStore())
    cfg = svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'haiku', 'oat-tok', **command_kwargs('example-org/acme'))
    assert cfg['credentialed'] is True
    assert creds.store['acme'] == 'oat-tok'

@intent('INT-FC-R114')
def test_set_agent_runs_the_same_preflight_before_seating_its_credential():
    driver_ok = FakeDriver(verdict=True)
    svc_ok = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), driver=driver_ok)
    saved = svc_ok.set_agent.execute('My Sub', 'claude', '', 'haiku', 'good-tok', **command_kwargs(''))
    assert saved['provider'] == 'claude'
    assert driver_ok.checked == ('good-tok', 'haiku', '')
    driver_bad = FakeDriver(verdict=False)
    svc_bad = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), driver=driver_bad)
    with pytest.raises(ValueError):
        svc_bad.set_agent.execute('My Sub', 'claude', '', 'haiku', 'bad-tok', **command_kwargs(''))

class _FakeProc:

    def __init__(self, returncode, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

@intent('INT-FC-R114')
def test_http_driver_agent_validate_folds_the_provider_answer(monkeypatch):
    agent = HttpDriverAgent()
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: _FakeProc(0, stdout='{"result": "ok"}'))
    assert agent.validate('sk-ant-api-good') is True
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: _FakeProc(1, stderr='API Error: 401 Invalid API key.'))
    assert agent.validate('sk-ant-api-bad') is False
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: _FakeProc(1, stderr='getaddrinfo ENOTFOUND api.example.com'))
    assert agent.validate('sk-ant-api-unreachable') is None

    def _raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd='claude', timeout=20)
    monkeypatch.setattr(subprocess, 'run', _raise_timeout)
    assert agent.validate('sk-ant-api-slow') is None
    assert agent.validate('') is False
