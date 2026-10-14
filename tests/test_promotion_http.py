"""The promotion door over HTTP: the derived rows reach the pane, and a console
with no promotion source says undeclared rather than inventing an empty queue."""
from fastapi.testclient import TestClient
from orchestrator.adapters.inbound.http.app import create_app
from capability_support import make_capabilities
from promotion_support import observe_promotion
from tests.test_promotion_service import FakeMaintenance, FakePromotionSource, FakeRepos

def _client(psource) -> TestClient:
    service = make_capabilities(FakeRepos(), msource=FakeMaintenance(['v1.42.0']), psource=psource)
    observe_promotion(service, 'platform-studio')
    return TestClient(create_app(service))

def test_the_door_serves_the_derived_rows() -> None:
    response = _client(FakePromotionSource()).get('/api/promotion/state', params={'repo': 'platform-studio'})
    assert response.status_code == 200
    body = response.json()
    assert body['declared'] is True and body['proven'] == '1.42.0'
    rows = {row['name']: row for row in body['targets']}
    assert rows['example-prod']['state'] == 'pending'
    assert rows['example-prod']['destination'] == 'example / prod'
    assert rows['partner']['door'] == 'pull-request'
    assert rows['partner']['terms'] == 'source'

def test_a_malformed_contract_reports_the_malformation() -> None:
    broken = FakePromotionSource(contract='targets:\n  - name: nameless-kind\n')
    body = _client(broken).get('/api/promotion/state', params={'repo': 'platform-studio'}).json()
    assert body['declared'] is True
    assert 'missing name or kind' in body['problem']

def test_an_app_without_a_contract_is_not_a_promotion_subject() -> None:
    body = _client(FakePromotionSource(contract=None)).get('/api/promotion/state', params={'repo': 'platform-studio'}).json()
    assert body['declared'] is False and body['targets'] == []

def test_the_contract_shape_the_scaffold_ships_declares_nothing() -> None:
    scaffolded = FakePromotionSource(contract='# the shape, as comments\ntargets: []\n')
    body = _client(scaffolded).get('/api/promotion/state', params={'repo': 'platform-studio'}).json()
    assert body['declared'] is True and body['problem'] == '' and (body['targets'] == [])

def test_a_console_without_the_source_says_undeclared() -> None:
    service = make_capabilities(FakeRepos())
    body = TestClient(create_app(service)).get('/api/promotion/state', params={'repo': 'platform-studio'}).json()
    assert body['declared'] is False
