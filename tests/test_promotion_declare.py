"""Declaring a target: what the contract will and will not admit, and the file
the console writes when it does."""
import pytest
from fastapi.testclient import TestClient
from orchestrator.adapters.inbound.http.app import create_app
from orchestrator.application.promotion import parse_contract
from orchestrator.application.promotion_declare import ContractError, declare_target, render_contract
from capability_support import make_capabilities
from promotion_support import observe_promotion
from orchestrator.domain.model.target_kind import TargetKind
from tests.test_promotion_service import FakeMaintenance, FakeRepos

class WritingSource:
    """A promotion source that remembers what was committed to the app."""

    def __init__(self, contract='targets: []\n', installs=None):
        self.contract = contract
        self.installs = installs if installs is not None else {'chaos': ['prod'], 'example': ['prod', 'uat']}
        self.written: list[tuple[str, str, str]] = []

    def repository_revision(self, repo):
        return "base-head"

    def contract_text(self, repo, *, revision=""):
        assert not revision or revision == "base-head"
        return self.contract

    def deploy_installs(self, repo):
        return self.installs

    def write_contract(self, repo, text, message, author='', *, expected_revision):
        assert expected_revision == 'base-head'
        self.written.append((text, message, author))
        self.contract = text
        return 'abc1234'

    def environment_values(self, repo, install, environment):
        return 'app:\n  image:\n    tag: 1.0.0\n'

    def open_door(self, repo, base, credential=''):
        return ''

    def last_merged_release(self, repo, base, credential=''):
        return ''

    def probe(self, url):
        return True

def _client(source):
    service = make_capabilities(FakeRepos(), msource=FakeMaintenance(['v1.42.0']), psource=source)
    observe_promotion(service, 'acme')
    return (TestClient(create_app(service)), service)

class TestRules:

    def test_an_environment_target_carries_the_kind_s_definitions(self) -> None:
        target, = declare_target(existing=[], name='example-uat', kind='environment', install='example', environment='uat')
        assert target.kind is TargetKind.ENVIRONMENT
        assert (target.door, target.terms, target.acceptance) == ('commit', 'version', 'none')

    def test_an_entry_environment_is_refused_with_the_reason(self) -> None:
        with pytest.raises(ContractError, match='entry environment'):
            declare_target(existing=[], name='chaos-prod', kind='environment', install='chaos', environment='prod', entry_environments={'chaos': 'prod'})

    def test_a_pair_without_a_credential_name_is_refused(self) -> None:
        with pytest.raises(ContractError, match='name the credential'):
            declare_target(existing=[], name='partner', kind='repository', repo='their-org/their-repo', branch='main')

    def test_a_duplicate_name_and_a_duplicate_destination_are_both_refused(self) -> None:
        first = declare_target(existing=[], name='example-uat', kind='environment', install='example', environment='uat')
        with pytest.raises(ContractError, match='already declares a target named'):
            declare_target(existing=first, name='example-uat', kind='environment', install='example', environment='uat')
        with pytest.raises(ContractError, match='already declared as a target'):
            declare_target(existing=first, name='other', kind='environment', install='example', environment='uat')

class TestRoundTrip:

    def test_what_the_console_writes_is_what_the_parser_reads(self) -> None:
        targets = declare_target(existing=[], name='example-uat', kind='environment', install='example', environment='uat')
        targets = declare_target(existing=targets, name='partner', kind='repository', repo='their-org/their-repo', branch='main', credential='partner-pair', probe_url='https://their-host.example')
        read, problem = parse_contract(render_contract(targets))
        assert problem == ''
        assert [t.name for t in read] == ['example-uat', 'partner']
        pair = read[1]
        assert (pair.repo, pair.branch, pair.credential) == ('their-org/their-repo', 'main', 'partner-pair')
        assert (pair.acceptance, pair.probe_url) == ('probe', 'https://their-host.example')

class TestDoor:

    def test_the_options_offer_only_what_exists_and_never_the_entry(self) -> None:
        client, _ = _client(WritingSource())
        body = client.get('/api/promotion/options', params={'repo': 'acme'}).json()
        by_install = {row['install']: row for row in body['installs']}
        assert body['readable'] is True
        assert by_install['chaos']['environments'] == []
        assert by_install['chaos']['entry'] == 'prod'
        assert by_install['example']['environments'] == ['prod', 'uat']

    def test_declaring_a_target_commits_the_contract_and_returns_the_state(self) -> None:
        source = WritingSource()
        client, _ = _client(source)
        response = client.post('/api/promotion/target', json={'repo': 'acme', 'name': 'partner', 'kind': 'repository', 'pair_repo': 'their-org/their-repo', 'branch': 'main', 'credential': 'partner-pair', 'author': 'rafael'})
        assert response.status_code == 200
        body = response.json()
        assert body['target'] == 'partner' and body['commit'] == 'abc1234'
        text, message, author = source.written[0]
        assert 'their-org/their-repo' in text and 'credential: partner-pair' in text
        assert message == 'feat(promotion): declare the partner target'
        assert author == 'rafael'
        assert [row['name'] for row in body['targets']] == ['partner']

    def test_a_refused_declaration_answers_422_with_the_reason(self) -> None:
        client, _ = _client(WritingSource())
        response = client.post('/api/promotion/target', json={'repo': 'acme', 'name': 'chaos-prod', 'kind': 'environment', 'install': 'chaos', 'environment': 'prod'})
        assert response.status_code == 422
        assert 'entry environment' in response.json()['detail']

    def test_a_malformed_contract_blocks_the_act_rather_than_overwriting_it(self) -> None:
        client, _ = _client(WritingSource(contract='targets:\n  - name: half\n'))
        response = client.post('/api/promotion/target', json={'repo': 'acme', 'name': 'partner', 'kind': 'repository', 'pair_repo': 'o/r', 'branch': 'main', 'credential': 'c'})
        assert response.status_code == 422
        assert 'malformed' in response.json()['detail']
