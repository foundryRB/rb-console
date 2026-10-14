from capability_support import with_lifecycle
from orchestrator.domain.model.repository_inventory_entry import RepositoryInventoryEntry
from delivery_fixtures import record_inputs
"""Integration test for the REST door: it mirrors the core (health, config refusal,
plan a scope launch) over HTTP via TestClient."""
import threading
import time
from pathlib import Path
from fastapi.testclient import TestClient
from pytest_intent import intent
from orchestrator.adapters.inbound.http.app import create_app
from orchestrator.adapters.outbound.memory.index import DeliveryIndex
from orchestrator.domain.services.delivery_resolution import derive_from_records
from capability_support import make_capabilities

class FakeRepos:

    def __init__(self, tmp):
        self.tmp = Path(tmp)

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        p = self.tmp / target
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    def register(self, workspace, request='', source=(), source_name=''):
        scratch = Path(workspace) / '.delivery'
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / 'README.md').write_text('s', encoding='utf-8')
        if request:
            (scratch / 'request.md').write_text(request, encoding='utf-8')

    def close_line(self, workspace, *, expected_revision=''):
        import shutil
        shutil.rmtree(Path(workspace) / '.delivery', ignore_errors=True)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

@intent('INT-FC-R13')
def test_rest_door_mirrors_the_core(tmp_path):
    client = TestClient(create_app(make_capabilities(FakeRepos(tmp_path))))
    assert client.get('/api/health').json()['status'] == 'ok'
    refused = client.post('/api/start', json={'target': 'acme', 'config': {}})
    assert refused.status_code == 422
    ok = client.post('/api/start', json={'target': 'acme', 'config': {'worker_credential': 'tok', 'repo_target': 'acme', 'repo_rights': True}})
    assert ok.status_code == 200
    body = ok.json()
    assert body['kind'] == 'launch'
    assert body['launch']['skill'] == 'deliver-engagement'

def _spa_client(tmp_path, monkeypatch):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<!doctype html><title>Foundry Console</title>', encoding='utf-8')
    monkeypatch.setenv('FC_FRONTEND_DIST', str(dist))
    return TestClient(create_app(make_capabilities(FakeRepos(tmp_path))))

@intent('INT-FC-R32')
def test_backend_routes_are_separate_from_browser_shell(tmp_path, monkeypatch):
    client = _spa_client(tmp_path, monkeypatch)
    r = client.get('/settings')
    assert r.status_code == 404
    assert client.get('/').status_code == 404

@intent('INT-FC-R33')
def test_mcp_doors_are_derived_and_exclude_non_doors(tmp_path, monkeypatch):
    client = _spa_client(tmp_path, monkeypatch)
    doors = client.get('/api/config/mcp-doors').json()['doors']
    assert doors == ['playbook-studio', 'estimatekit', 'protopane', 'platform-studio']
    assert 'csd' not in doors

@intent('INT-FC-R37')
def test_establish_is_deterministic_credential_free_and_captures_the_request(tmp_path, monkeypatch):
    client = _spa_client(tmp_path, monkeypatch)
    r = client.post('/api/establish', json={'target': 'acme', 'request': 'Build a store for Acme'})
    assert r.status_code == 200
    assert r.json()['exists'] is True
    req = tmp_path / 'acme' / '.delivery' / 'request.md'
    assert req.exists() and 'Acme' in req.read_text(encoding='utf-8')

@intent('INT-FC-R79')
def test_close_line_closes_the_line_over_http(tmp_path, monkeypatch):
    client = _spa_client(tmp_path, monkeypatch)
    client.post('/api/establish', json={'target': 'acme', 'request': 'Build a store'})
    assert (tmp_path / 'acme' / '.delivery').exists()
    r = client.post('/api/deliveries/close', json={'target': str(tmp_path / 'acme')})
    assert r.status_code == 200
    assert r.json()['exists'] is False
    assert not (tmp_path / 'acme' / '.delivery').exists()
    again = client.post('/api/deliveries/close', json={'target': str(tmp_path / 'acme')})
    assert again.status_code == 422

class MutableSource:
    """An org whose repo list changes between scans, so the warm-cache read (GET) and the
    explicit rescan (POST /api/fleet/refresh) are distinguishable on the wire."""

    def __init__(self):
        self.rows = [RepositoryInventoryEntry('example-org/one', 'one', 't1', (), '')]

    def scan(self):
        return []

    def state_of(self, repo):
        return derive_from_records(repo, False, record_inputs({}))

    def list_org_repos(self):
        return list(self.rows)

class GatedSource(MutableSource):
    """A source whose scan blocks until released, so "the request never waits for the
    rescan" (INT-FC-R107) is a testable difference rather than a claim: a handler that
    awaits the scan inline cannot answer at all until the gate opens."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()
        self.scanning = threading.Event()

    def scan(self):
        self.scanning.set()
        self.gate.wait(10)
        return []

class BoomSource(MutableSource):
    """A source whose scan raises - the per-repo .delivery/ probe hitting a bad token or
    a rate limit - so the rescan's error has a path to the operator with no response of
    its own left to fail on."""

    def scan(self):
        raise RuntimeError('github said no')

def _names(body):
    return sorted((p['name'] for p in body['projects']))

def _await_http_turn(client, turn_id, timeout=5.0):
    """Poll a started turn to its terminal state over HTTP (the SPA's loop, compressed) -
    the same shape test_copilot.py's _await_turn polls at the service layer."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = client.get(f'/api/chat/turns/{turn_id}').json()
        if out['status'] != 'running':
            return out
        time.sleep(0.01)
    raise AssertionError('the turn never finished')

@intent('INT-FC-R107')
def test_fleet_refresh_is_an_explicit_rescan_and_reads_stay_cached(tmp_path):
    src = MutableSource()
    svc = make_capabilities(FakeRepos(tmp_path), index=DeliveryIndex(), source=src)
    svc.refresh.execute()
    client = TestClient(create_app(svc))
    assert _names(client.get('/api/fleet').json()) == ['one']
    src.rows.append(RepositoryInventoryEntry('example-org/two', 'two', 't2', (), ''))
    assert _names(client.get('/api/fleet').json()) == ['one']
    start = client.post('/api/fleet/refresh').json()
    assert set(start) == {'turn'}
    done = _await_http_turn(client, start['turn'])
    assert done['status'] == 'done'
    assert _names(done) == ['one', 'two']
    assert _names(client.get('/api/fleet').json()) == ['one', 'two']

@intent('INT-FC-R107')
def test_the_fleet_rescan_is_never_awaited_on_the_request_that_starts_it(tmp_path):
    """The clause the shape assertion above cannot hold: answering {"turn": id} proves
    nothing if the handler scanned the org first. Hold the scan open and the difference
    is decisive - the POST must answer, and the poll must read 'running', while the
    rescan is still in flight. A handler that awaits it inline cannot do either."""
    src = GatedSource()
    svc = make_capabilities(FakeRepos(tmp_path), index=DeliveryIndex(), source=src)
    src.gate.set()
    svc.refresh.execute()
    src.gate.clear()
    src.scanning.clear()
    client = TestClient(create_app(svc))
    src.rows.append(RepositoryInventoryEntry('example-org/two', 'two', 't2', (), ''))
    start = client.post('/api/fleet/refresh').json()
    assert set(start) == {'turn'}
    assert src.scanning.wait(5)
    assert not src.gate.is_set()
    assert client.get(f"/api/chat/turns/{start['turn']}").json() == {'status': 'running'}
    src.gate.set()
    assert _names(_await_http_turn(client, start['turn'])) == ['one', 'two']

@intent('INT-FC-R107')
def test_a_failed_fleet_rescan_lands_as_the_turn_s_error(tmp_path):
    """The rescan's error must reach the operator through the poll: off the wire, a
    scan that raises has no response left to fail, so the turn carries it instead."""
    svc = make_capabilities(FakeRepos(tmp_path), index=DeliveryIndex(), source=BoomSource())
    client = TestClient(create_app(svc))
    start = client.post('/api/fleet/refresh')
    assert start.status_code == 200 and set(start.json()) == {'turn'}
    done = _await_http_turn(client, start.json()['turn'])
    assert done['status'] == 'error' and 'github said no' in done['error']

def _await_ready(client, timeout=5.0):
    """Poll /api/ready to its 200, the way the kubelet's readiness probe would."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get('/api/ready').status_code == 200:
            return True
        time.sleep(0.01)
    return False

@intent('INT-FC-R125')
def test_readiness_waits_for_the_first_refresh_tick_while_liveness_never_does(tmp_path):
    """The warm-up window made visible: the door is serving, the first refresh has not
    landed, and readiness must say so - else the Service routes a fleet read to a pod
    whose cache is still cold and the empty state blames the git token for it (#64).
    `with` runs the lifespan, so the background refresher really ticks; the gated source
    holds that first tick open, which is what makes the window observable at all."""
    src = GatedSource()
    svc = make_capabilities(FakeRepos(tmp_path), index=DeliveryIndex(), source=src)
    with TestClient(create_app(svc)) as client:
        assert src.scanning.wait(5)
        assert client.get('/api/ready').status_code == 503
        assert client.get('/api/health').status_code == 200
        src.gate.set()
        assert _await_ready(client)
        assert _names(client.get('/api/fleet').json()) == ['one']

@intent('INT-FC-R125')
def test_a_first_refresh_that_fails_still_makes_the_pod_ready(tmp_path):
    """The constraint that decides the contract: the gate is "the first refresh
    finished", never "the fleet is non-empty". An install with no git token (or a bad
    one) has an empty fleet CORRECTLY, and that is precisely when the empty state's
    "set the git token" message is the right thing to show - so a pod whose scan fails
    must still go ready and still serve that read, or it would never be routed to and
    never able to show the operator the advice it is deadlocked on."""
    svc = make_capabilities(FakeRepos(tmp_path), index=DeliveryIndex(), source=BoomSource())
    with TestClient(create_app(svc)) as client:
        assert _await_ready(client)
        assert _names(client.get('/api/fleet').json()) == []

@intent('INT-FC-R159')
def test_the_session_door_reports_the_gate_and_names_the_proxy_route(tmp_path, monkeypatch):
    """The half of INT-FC-R159 the door owns: Settings asks whether a session exists to
    end, and the answer is the install's own gate - the chart value that also decides
    whether the proxy sidecar is there at all. The route is NAMED, never composed in the
    view, because the console neither serves it nor ends anything itself."""
    monkeypatch.setenv('FC_OIDC_ENABLED', 'true')
    client = TestClient(create_app(make_capabilities(FakeRepos(tmp_path))))
    monkeypatch.setenv('FC_ORG', 'example-org')
    monkeypatch.setenv('FC_OIDC_ISSUER', 'https://identity.example/realm')
    monkeypatch.setenv('FC_PROXY_SECRET', 'unit-key')
    gated = client.get('/api/config/session', headers={'X-Auth-Request-User': 'operator-1', 'X-Console-Proxy-Secret': 'unit-key'}).json()
    assert gated == {'oidc_enabled': True, 'sign_out_url': '/oauth2/sign_out', 'teams_enabled': False, 'admin': True, 'teams': [], 'user': ''}

@intent('INT-FC-R159')
def test_an_install_with_no_gate_offers_no_route_to_sign_out_of(tmp_path, monkeypatch):
    """With no proxy in front there is no session to end, so the door reports none and the
    card does not render. A default of ON would have every open install showing a control
    that 404s - worse than showing none - so the flag's absence reads as off."""
    client = TestClient(create_app(make_capabilities(FakeRepos(tmp_path))))
    monkeypatch.delenv('FC_OIDC_ENABLED', raising=False)
    assert client.get('/api/config/session').json() == {'oidc_enabled': False, 'sign_out_url': '', 'teams_enabled': False, 'admin': True, 'teams': [], 'user': ''}
    monkeypatch.setenv('FC_OIDC_ENABLED', 'false')
    assert client.get('/api/config/session').json()['oidc_enabled'] is False

@intent('INT-FC-R176')
def test_the_browsers_drive_body_drives_without_asserting_a_write_right(tmp_path, monkeypatch):
    """The cockpit's exact Drive request (DeliveryDetailPage.drivePhase): no credential,
    no repo_rights. The right is the drive's own once the caller is admitted; the 6.18.0
    regression was this body refused with 'config incomplete: a repo target and its rights
    are required' on every line, while every test built its RunConfig with the right set
    and the one browser test of the route stubbed the server."""
    from tests.test_maintenance_service import FakeCredentials
    from tests.test_redrive import OrderedRepos, OrderedWorkflows, RefSource
    monkeypatch.chdir(tmp_path)
    scratch = tmp_path / 'org' / 'app' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    order: list[str] = []
    svc = make_capabilities(OrderedRepos(order), workflows=OrderedWorkflows(order), source=RefSource(), credentials=FakeCredentials(persisted=True))
    client = TestClient(create_app(svc))
    r = client.post('/api/deliveries/drive', json={'target': 'org/app', 'config': {'worker_credential': None, 'repo_target': 'org/app'}, 'from_phase': None, 'feedback': None})
    assert r.status_code == 200, r.text
    assert r.json()['run_id'] and order == ['submit']
