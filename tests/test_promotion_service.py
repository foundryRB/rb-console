from maintenance_fixtures import semantic_pr
"""The promotion mode's service half: the contract read off the repo host becomes
the pane's rows, the queue leads, and an app with no contract is not a subject."""
from capability_support import make_capabilities
from promotion_support import observe_promotion

class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeMaintenance:
    """Only the leg the promotion view uses: the tags the release train reads."""

    def __init__(self, tags):
        self._tags = tags

    def tags(self, repo):
        return self._tags
CONTRACT = '\ntargets:\n  - name: example-prod\n    kind: environment\n    install: example\n    environment: prod\n  - name: partner\n    kind: repository\n    repo: their-org/their-repo\n    branch: main\n    credential: partner\n'

class FakePromotionSource:
    """The app's own repo: its contract and its deploy branches. A pair's repository is
    reached through the DOOR beside it (#167), never from here."""

    def __init__(self, contract=CONTRACT, env_values='a:\n  image:\n    tag: 1.39.2\n'):
        self._contract, self._values = (contract, env_values)

    def contract_text(self, repo):
        return self._contract

    def deploy_installs(self, repo):
        return {'example': ['prod', 'staging']}

    def environment_values(self, repo, install, environment):
        return self._values

    def probe(self, url):
        return True

class FakeDoor:
    """The pair's own pull requests, in the listings the derivation folds: the promote
    branch names the release, so a merged door IS what the pair accepted."""

    def __init__(self, door='', merged='1.38.0'):
        self._door, self._merged = (door, merged)

    def pull_request(self, repo, number, credential):
        return None

    def open_pull_requests(self, repo, base, credential):
        if not self._door:
            return tuple(semantic_pr(record) for record in ([]))
        return tuple(semantic_pr(record) for record in ([{'number': int(self._door.split()[-1]), 'head': {'ref': 'promote/1.42.0'}}]))

    def closed_pull_requests(self, repo, base, credential):
        if not self._merged:
            return tuple(semantic_pr(record) for record in ([]))
        return tuple(semantic_pr(record) for record in ([{'number': 1, 'merged_at': '2026-08-01', 'head': {'ref': f'promote/{self._merged}'}}]))

def _service(psource, tags=('v1.42.0', 'v1.39.2'), door=None):
    from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
    config = InMemoryConfigStore()
    config.put_setting('pair-partner', {'name': 'partner'}, 'pair-grant')
    service = make_capabilities(FakeRepos(), config=config, msource=FakeMaintenance(list(tags)), psource=psource, door=door if door is not None else FakeDoor())
    observe_promotion(service, 'platform-studio')
    return service

def test_the_contract_becomes_rows_carrying_their_declared_definitions() -> None:
    state = _service(FakePromotionSource()).promotion_state.execute('platform-studio')
    assert state['declared'] is True
    assert state['proven'] == '1.42.0'
    rows = {r['name']: r for r in state['targets']}
    assert rows['example-prod']['destination'] == 'example / prod'
    assert (rows['example-prod']['door'], rows['example-prod']['terms']) == ('commit', 'version')
    assert (rows['partner']['door'], rows['partner']['terms']) == ('pull-request', 'source')
    assert rows['example-prod']['state'] == 'pending'
    assert rows['example-prod']['accepted'] == '1.39.2'

def test_an_open_door_reports_in_flight_and_leads_the_rows() -> None:
    state = _service(FakePromotionSource(), door=FakeDoor(door='PR 14')).promotion_state.execute('platform-studio')
    first = state['targets'][0]
    assert (first['name'], first['state'], first['door_ref']) == ('partner', 'in-flight', 'PR 14')

def test_an_app_without_a_contract_is_not_a_promotion_subject() -> None:
    state = _service(FakePromotionSource(contract=None)).promotion_state.execute('platform-studio')
    assert state['declared'] is False
    assert state['targets'] == []

def test_a_console_without_the_source_says_undeclared_rather_than_empty() -> None:
    bare = make_capabilities(FakeRepos())
    assert bare.promotion_state.execute('platform-studio')['declared'] is False
