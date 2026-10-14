from maintenance_fixtures import semantic_pr
"""Pair credentials: the repo-host credential for the FAR side of a pair, which a
`kind: repository` promotion target names and the platform held nowhere (issue #131).

Two things are under test and they are not the same thing. One is the registry: a
supplied secret registered under the name the app's own contract writes down, never
minted, never listed back. The other is what the surfaces do with it - a target whose
credential is not held is a door that cannot be opened, and it must read differently
from one that works, which was the whole defect: nothing tried, so nothing differed.

Audit: csd-intent .
"""
from capability_support import invoke_helper
from capability_support import command_kwargs
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.application.promotion import promotion_view
from capability_support import make_capabilities
from orchestrator.domain.model.promotion_state import PromotionState
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.model.target_kind import TargetKind
from orchestrator.domain.promotion import derive_position

class FakeRepos:

    def list_delivery_repos(self):
        return []

def _svc():
    return make_capabilities(FakeRepos(), config=InMemoryConfigStore())
CONTRACT = 'targets:\n  - name: partner\n    kind: repository\n    repo: their-org/their-repo\n    branch: main\n    credential: partner-pair\n    door: pull-request\n    terms: source\n    acceptance: none\n'

class FakeSource:
    """The app's own repo: its contract and its deploy branches. A pair's repository is
    not reachable from here at all any more - that is the door's (#167)."""

    def __init__(self, contract=CONTRACT):
        self.contract = contract

    def contract_text(self, repo):
        return self.contract

    def environment_values(self, repo, install, environment):
        return 'tag: 1.0.0\n'

    def probe(self, url):
        return True

    def read_suite(self, url, match=''):
        return True

class FakeDoor:
    """A door that RECORDS what it was asked, so a test can prove the pair was never read
    rather than merely that the row came out unreadable."""

    def __init__(self, accepted='1.0.0', open_ref=''):
        self._closed = [{'number': 1, 'merged_at': '2026-08-01', 'head': {'ref': f'promote/{accepted}'}}] if accepted else []
        self._open = [{'number': int(open_ref.split()[-1]), 'head': {'ref': 'promote/2.1.0'}}] if open_ref else []
        self.asked: list[tuple] = []

    def pull_request(self, repo, number, credential):
        self.asked.append(('pull_request', repo, credential))
        return None

    def open_pull_requests(self, repo, base, credential):
        self.asked.append(('open_pull_requests', repo, credential))
        return (None if (records := (self._open)) is None else tuple(semantic_pr(record) for record in records))

    def closed_pull_requests(self, repo, base, credential):
        self.asked.append(('closed_pull_requests', repo, credential))
        return (None if (records := (self._closed)) is None else tuple(semantic_pr(record) for record in records))

@intent('INT-FC-R126')
def test_a_pair_credential_is_registered_listed_and_deleted_without_exposing_the_secret():
    svc = _svc()
    svc.set_pair_credential.execute('partner-pair', 'github.com', 'foundry-delivery-bot', 'pat-PAIR', **command_kwargs(''))
    held = svc.list_pair_credentials.execute()
    assert len(held) == 1
    assert held[0]['name'] == 'partner-pair' and held[0]['host'] == 'github.com'
    assert held[0]['configured'] is True
    assert 'pat-PAIR' not in str(held)
    assert svc.pair_credential_held.execute('partner-pair') is True
    assert svc.pair_credential_ref.execute('partner-pair') == 'fc-pair-partner-pair-key'
    assert svc.pair_credential_secret.execute('partner-pair') == 'pat-PAIR'
    svc.delete_pair_credential.execute('partner-pair', **command_kwargs(''))
    assert svc.list_pair_credentials.execute() == []
    assert svc.pair_credential_held.execute('partner-pair') is False
    assert svc.pair_credential_ref.execute('partner-pair') == ''

@intent('INT-FC-R126')
def test_registering_without_a_secret_is_refused_but_amending_a_held_one_is_not():
    svc = _svc()
    with pytest.raises(ValueError):
        svc.set_pair_credential.execute('partner-pair', 'github.com', '', None, **command_kwargs(''))
    assert svc.pair_credential_held.execute('partner-pair') is False
    svc.set_pair_credential.execute('partner-pair', '', '', 'pat-PAIR', **command_kwargs(''))
    assert svc.list_pair_credentials.execute()[0]['host'] == 'github.com'
    svc.set_pair_credential.execute('partner-pair', 'gitlab.com', '', None, **command_kwargs(''))
    assert svc.list_pair_credentials.execute()[0]['host'] == 'gitlab.com'
    assert svc.pair_credential_secret.execute('partner-pair') == 'pat-PAIR'
    with pytest.raises(ValueError):
        svc.set_pair_credential.execute('', '', '', 'pat-X', **command_kwargs(''))

@intent('INT-FC-R126')
def test_a_pair_credential_is_never_one_of_ours():
    """A pair credential's login must NOT join the set the maintenance derivation reads as
    driven-by-us: a review by their organization is not our own fresh pass. This is the one
    behavioural difference that keeps the registry from being a second git-identity family."""
    svc = _svc()
    svc.set_git_identity.execute('Foundry Delivery', 'd@x', 'foundry-delivery-bot', 'pat-A', **command_kwargs(''))
    svc.set_git_roles.execute({'programmer': 'Foundry Delivery'}, **command_kwargs(''))
    svc.set_pair_credential.execute('partner-pair', 'github.com', 'their-bot', 'pat-PAIR', **command_kwargs(''))
    assert invoke_helper(svc, '_shared_identities') == {'foundry-delivery-bot'}
    assert all((r['key'] != 'partner-pair' for r in svc.git_role_catalog.execute()))

@intent('INT-FC-R127')
def test_a_shut_door_is_unreadable_with_its_own_reason_and_outranks_every_other_rule():
    target = PromotionTarget(name='partner', kind=TargetKind.REPOSITORY, door='pull-request', terms='source', acceptance='none', repo='their-org/their-repo', branch='main', credential='partner-pair')
    position = derive_position(target=target, proven='2.1.0', accepted='2.1.0', door_shut='the platform holds no credential named partner-pair')
    assert position.state is PromotionState.UNREADABLE
    assert position.door_shut is True
    assert position.detail == 'the door cannot be opened: the platform holds no credential named partner-pair'
    assert position.accepted == '' and position.door_ref == ''
    assert derive_position(target=target, proven='2.1.0', accepted=None, door_open='PR 14', door_shut='no credential').state is PromotionState.UNREADABLE

@intent('INT-FC-R127')
def test_an_unheld_credential_shuts_the_door_and_the_pair_is_never_read():
    svc = _svc()
    door = FakeDoor()
    view = promotion_view(repo='org/app', proven='2.1.0', source=FakeSource(), registered=svc.pair_credential_held.execute, door=door)
    position = view['positions'][0]
    assert position.door_shut is True
    assert position.detail == 'the door cannot be opened: the platform holds no credential named partner-pair'
    assert door.asked == []
    assert [p.target.name for p in view['queue']] == ['partner']

@intent('INT-FC-R127')
def test_a_held_credential_opens_the_door_and_the_pair_reads_ride_it():
    svc = _svc()
    svc.set_pair_credential.execute('partner-pair', 'github.com', '', 'pat-PAIR', **command_kwargs(''))
    door = FakeDoor(accepted='2.1.0')
    view = promotion_view(repo='org/app', proven='2.1.0', source=FakeSource(), registered=svc.pair_credential_held.execute, door=door)
    position = view['positions'][0]
    assert position.door_shut is False
    assert position.state is PromotionState.CURRENT
    assert {call[2] for call in door.asked} == {'partner-pair'}

@intent('INT-FC-R127')
def test_a_contract_naming_no_credential_is_shut_too():
    source = FakeSource(contract=CONTRACT.replace('    credential: partner-pair\n', ''))
    view = promotion_view(repo='org/app', proven='2.1.0', source=source, registered=lambda name: True)
    assert view['positions'][0].detail == 'the door cannot be opened: the contract names no credential for this pair'

@intent('INT-FC-R127')
def test_an_environment_target_is_never_shut_and_an_unasked_question_is_never_a_no():
    environment = 'targets:\n  - name: example-prod\n    kind: environment\n    install: example\n    environment: prod\n    door: commit\n    terms: version\n    acceptance: none\n'
    view = promotion_view(repo='org/app', proven='1.0.0', source=FakeSource(contract=environment), registered=lambda name: False)
    assert view['positions'][0].door_shut is False
    assert view['positions'][0].state is PromotionState.CURRENT
    unasked = promotion_view(repo='org/app', proven='2.1.0', source=FakeSource(), registered=None)
    assert unasked['positions'][0].door_shut is False

@intent('INT-FC-R127')
def test_the_registered_host_is_what_the_door_selects_on():
    """The middle link of what makes the door selected per app (#167): the contract names
    the credential, the registration names the host, the host names the implementation.
    The adapter's own never-borrow-our-token rule is held in ``test_door.py``, where that
    code now lives."""
    svc = _svc()
    svc.set_pair_credential.execute('partner-pair', '', '', 'pat-PAIR', **command_kwargs(''))
    assert svc.pair_credential_host.execute('partner-pair') == 'github.com'
    svc.set_pair_credential.execute('partner-pair', 'dev.azure.com', '', None, **command_kwargs(''))
    assert svc.pair_credential_host.execute('partner-pair') == 'dev.azure.com'
    assert svc.pair_credential_host.execute('never-registered') == 'github.com'

def test_pair_credentials_round_trip_over_the_rest_door():
    from fastapi.testclient import TestClient
    from orchestrator.adapters.inbound.http.app import create_app
    client = TestClient(create_app(_svc()))
    r = client.post('/api/config/pair-credentials', json={'name': 'partner-pair', 'host': 'github.com', 'login': 'their-bot', 'token': 'pat-PAIR'})
    assert r.status_code == 200 and r.json()['configured'] is True
    assert 'pat-PAIR' not in r.text
    listed = client.get('/api/config/pair-credentials').json()['credentials']
    assert [c['name'] for c in listed] == ['partner-pair']
    assert 'pat-PAIR' not in client.get('/api/config/pair-credentials').text
    refused = client.post('/api/config/pair-credentials', json={'name': 'other-pair'})
    assert refused.status_code == 422 and 'secret' in refused.json()['detail']
    assert client.delete('/api/config/pair-credentials/partner-pair').json() == {'deleted': 'partner-pair'}
    assert client.get('/api/config/pair-credentials').json()['credentials'] == []
