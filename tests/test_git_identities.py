"""Per-phase git identities: named machine-user credentials (name + email + login + PAT),
assigned to Job phases and the console's own acts through a runtime role map. The point is
that the reviewer can be a DIFFERENT GitHub account than the resolver, because GitHub refuses
to let an account approve its own PR. Audit: csd-intent ."""
from capability_support import invoke_helper
from capability_support import command_kwargs
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.adapters.outbound.argo.maintenance_launch import compile_maintenance_workflow
from capability_support import make_capabilities
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig

class FakeRepos:

    def list_delivery_repos(self):
        return []

def _svc():
    return make_capabilities(FakeRepos(), config=InMemoryConfigStore())

def _env(workflow, step):
    """The env of one worker step, as a {name: entry} dict."""
    for t in workflow['spec']['templates']:
        if t['name'] == step:
            return {e['name']: e for e in t['container']['env']}
    raise AssertionError(f'no {step} step in the workflow')

@intent('INT-FC-R88')
def test_git_identities_saved_listed_deleted_without_exposing_token():
    svc = _svc()
    svc.set_git_identity.execute('Foundry Delivery', '1+foundry-delivery-bot@users.noreply.github.com', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    ids = svc.list_git_identities.execute()
    assert len(ids) == 1
    a = ids[0]
    assert a['name'] == 'Foundry Delivery' and a['login'] == 'foundry-delivery-bot'
    assert a['configured'] is True
    assert 'pat-A' not in str(a)
    svc.set_git_identity.execute('Foundry Delivery', a['email'], 'foundry-delivery-bot', None, **command_kwargs(''))
    assert svc.list_git_identities.execute()[0]['configured'] is True
    with pytest.raises(ValueError):
        svc.set_git_identity.execute('', 'e@x', 'l', 't', **command_kwargs(''))
    svc.delete_git_identity.execute('Foundry Delivery', **command_kwargs(''))
    assert svc.list_git_identities.execute() == []

@intent('INT-FC-R90')
def test_role_map_assigns_identities_drops_unknown_and_clears_to_unassigned():
    svc = _svc()
    svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    svc.set_git_identity.execute('Foundry Review', 'r@x', 'foundry-review-bot', 'pat-B', **command_kwargs(''))
    keys = {r['key'] for r in svc.git_role_catalog.execute()}
    assert {'architect', 'librarian', 'programmer', 'reviewer', 'release-manager', 'console'} <= keys
    svc.set_git_roles.execute({'programmer': 'Foundry Delivery', 'reviewer': 'Foundry Review', 'console': 'Foundry Delivery', 'bogus-role': 'Foundry Delivery'}, **command_kwargs(''))
    roles = svc.git_roles.execute()
    assert roles['programmer'] == 'Foundry Delivery'
    assert roles['reviewer'] == 'Foundry Review'
    assert 'bogus-role' not in roles
    svc.set_git_roles.execute({'reviewer': 'Foundry Review'}, **command_kwargs(''))
    assert 'console' not in svc.git_roles.execute() and 'programmer' not in svc.git_roles.execute()

@intent('INT-FC-R89')
def test_compiler_injects_each_agents_identity_refs():
    """A one-shot resolve compiles resolve THEN review; each step must carry its OWN agent's
    identity (the Programmer's, then the Reviewer's) as ConfigMap+Secret refs, so the reviewer
    is a different account than the resolver. The map is keyed on the agent (issue #62)."""
    svc = _svc()
    svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    svc.set_git_identity.execute('Foundry Review', 'r@x', 'foundry-review-bot', 'pat-B', **command_kwargs(''))
    svc.set_git_roles.execute({'programmer': 'Foundry Delivery', 'reviewer': 'Foundry Review'}, **command_kwargs(''))
    wf = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.ONE_SHOT, RunConfig('tok', 'org/app', True), run_id='m1', git_identities=invoke_helper(svc, '_git_identities_map'))
    resolve, review = (_env(wf, 'worker-resolve'), _env(wf, 'worker-review'))
    assert resolve['FC_GIT_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-gitid-foundry-delivery-key'
    assert review['FC_GIT_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-gitid-foundry-review-key'
    assert resolve['FC_GIT_USER']['valueFrom']['configMapKeyRef']['name'] == 'fc-gitid-foundry-delivery'
    assert review['FC_GIT_EMAIL']['valueFrom']['configMapKeyRef']['name'] == 'fc-gitid-foundry-review'

@intent('INT-FC-R89')
def test_unassigned_agent_gets_no_git_identity():
    wf = compile_maintenance_workflow('org/app', 'review', 12, MaintenanceMode.GATED, RunConfig('tok', 'org/app', True), run_id='m2')
    env = _env(wf, 'worker-review')
    assert 'FC_GIT_USER' not in env
    assert 'FC_GIT_TOKEN' not in env
    assert 'FC_GIT_EMAIL' not in env

@intent('INT-FC-R92')
def test_console_acts_read_the_console_role_identity():
    svc = _svc()
    assert svc.console_identity_setting.execute() == ''
    svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    svc.set_git_roles.execute({'console': 'Foundry Delivery'}, **command_kwargs(''))
    assert svc.console_identity_setting.execute() == 'gitid-foundry-delivery'
    assert svc.set_setting.config.get_secret('gitid-foundry-delivery') == 'pat-A'

def test_identities_and_roles_round_trip_over_the_rest_door():
    from fastapi.testclient import TestClient
    from orchestrator.adapters.inbound.http.app import create_app
    client = TestClient(create_app(_svc()))
    r = client.post('/api/config/git-identities', json={'name': 'Foundry Review', 'email': 'r@x', 'login': 'foundry-review-bot', 'token': 'pat-B'})
    assert r.status_code == 200 and r.json()['configured'] is True and ('pat-B' not in r.text)
    client.post('/api/config/git-identities', json={'name': 'Foundry Delivery', 'email': 'd@x', 'login': 'foundry-delivery-bot', 'token': 'pat-A'})
    listed = client.get('/api/config/git-identities').json()['identities']
    assert {i['name'] for i in listed} == {'Foundry Review', 'Foundry Delivery'}
    roles_resp = client.get('/api/config/git-roles').json()
    assert any((r['key'] == 'console' for r in roles_resp['catalog']))
    put = client.post('/api/config/git-roles', json={'roles': {'programmer': 'Foundry Delivery', 'reviewer': 'Foundry Review'}}).json()
    assert put['roles']['reviewer'] == 'Foundry Review'
    assert client.delete('/api/config/git-identities/Foundry Review').json() == {'deleted': 'Foundry Review'}
    assert {i['name'] for i in client.get('/api/config/git-identities').json()['identities']} == {'Foundry Delivery'}

@intent('INT-FC-R91')
def test_shared_identities_is_the_set_of_assigned_logins():
    svc = _svc()
    svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    svc.set_git_identity.execute('Foundry Review', 'r@x', 'foundry-review-bot', 'pat-B', **command_kwargs(''))
    svc.set_git_roles.execute({'programmer': 'Foundry Delivery', 'reviewer': 'Foundry Review'}, **command_kwargs(''))
    assert invoke_helper(svc, '_shared_identities') == {'foundry-delivery-bot', 'foundry-review-bot'}
