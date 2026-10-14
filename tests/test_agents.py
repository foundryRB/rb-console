"""The agent registry: named, reusable model configs saved once, then selected (applied) to
the global driver or a delivery - so a credential is set once, not retyped. Audit: csd-intent ."""
from capability_support import command_kwargs
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from capability_support import make_capabilities

class FakeRepos:

    def list_delivery_repos(self):
        return []

@intent('INT-FC-R46')
def test_agent_registry_saves_lists_and_applies():
    config = InMemoryConfigStore()
    svc = make_capabilities(FakeRepos(), config=config)
    svc.set_agent.execute('My Claude', 'claude', '', 'haiku', 'oat-tok', **command_kwargs(''))
    agents = svc.list_agents.execute()
    assert len(agents) == 1
    a = agents[0]
    assert a['name'] == 'My Claude' and a['model'] == 'haiku' and (a['configured'] is True)
    assert 'oat-tok' not in str(a)
    d = svc.apply_agent_to_driver.execute('My Claude', **command_kwargs(''))
    assert d.configured is True and d.model == 'haiku' and (d.agent == 'My Claude')
    assert config.get_secret('driver') == 'oat-tok'
    assert svc.driver_config.execute().agent == 'My Claude'
    svc.set_agent.execute('My Sub', 'claude', '', 'haiku', 'sub-tok', ['haiku', 'sonnet'], **command_kwargs(''))
    sub = next((x for x in svc.list_agents.execute() if x['name'] == 'My Sub'))
    assert sub['models'] == ['haiku', 'sonnet']
    d2 = svc.apply_agent_to_driver.execute('My Sub', 'sonnet', **command_kwargs(''))
    assert d2.agent == 'My Sub' and d2.model == 'sonnet'
    assert config.get_secret('driver') == 'sub-tok'
    svc.set_agent.execute('Empty', 'claude', '', '', None, **command_kwargs(''))
    with pytest.raises(ValueError):
        svc.apply_agent_to_driver.execute('Empty', **command_kwargs(''))
    svc.delete_agent.execute('Empty', **command_kwargs(''))
    assert sorted((x['name'] for x in svc.list_agents.execute())) == ['My Claude', 'My Sub']

@intent('INT-FC-R73')
def test_one_saved_credential_backs_many_models():
    """The user's ask: one Claude sub (or one compatible endpoint+key) saved ONCE, then any of
    its models picked per use - not five credential sets to run five models on the same sub."""
    config = InMemoryConfigStore()

    class FakeCreds:

        def __init__(self):
            self.store = {}

        def put_delivery(self, slug, credential):
            self.store[slug] = credential

        def has_delivery(self, slug):
            return slug in self.store
    creds = FakeCreds()
    svc = make_capabilities(FakeRepos(), credentials=creds, config=config)
    a = svc.set_agent.execute('Claude sub', 'claude', '', 'haiku', 'one-token', ['haiku', 'sonnet', 'opus'], **command_kwargs(''))
    assert a['models'] == ['haiku', 'sonnet', 'opus']
    svc.apply_agent_to_delivery.execute('example-org/alpha', 'Claude sub', 'sonnet', **command_kwargs('example-org/alpha'))
    svc.apply_agent_to_delivery.execute('example-org/beta', 'Claude sub', 'opus', **command_kwargs('example-org/beta'))
    assert svc.delivery_config.execute('example-org/alpha')['model'] == 'sonnet'
    assert svc.delivery_config.execute('example-org/beta')['model'] == 'opus'
    assert creds.store == {'alpha': 'one-token', 'beta': 'one-token'}

class RefusingStore(InMemoryConfigStore):
    """A store whose deletes fail (the live one raises when RBAC forbids the verb)."""

    def delete_setting(self, name):
        raise RuntimeError('forbidden: cannot delete configmaps')

def test_a_failed_delete_surfaces_instead_of_reporting_success():
    """The API must never answer 'deleted' over a surviving agent: a live Role once
    lacked the delete verb, kubectl's failure was swallowed, and Settings' Delete
    button silently did nothing."""
    from fastapi.testclient import TestClient
    from orchestrator.adapters.inbound.http.app import create_app
    svc = make_capabilities(FakeRepos(), config=RefusingStore())
    svc.set_agent.execute('Doomed', 'claude', '', '', 'tok', **command_kwargs(''))
    client = TestClient(create_app(svc))
    resp = client.delete('/api/agents/Doomed')
    assert resp.status_code == 409
    assert resp.json()['code'] == 'operation_unknown'
    assert svc.list_agents.execute()[0]['name'] == 'Doomed'
