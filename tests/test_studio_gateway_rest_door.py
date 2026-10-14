from orchestrator.domain.model.platform_app import PlatformApp
"""The internal REST door seam: platform-studio calls ride REST, typed and unretried.

The Console's own platform-studio calls (the fleet read, pause/resume, the repo
scaffold) go over the studio's internal Service port, where a refusal is an HTTP
status with the exception class in the body - data, not a phrase to dig out of an
MCP ToolError string. A failed REST write has one outcome and is never dispatched
through another door. Audit: csd-intent .
"""
import io
import json
import re
import urllib.error
from pathlib import Path
from pytest_intent import intent
import pytest
from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway
from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
_MODULE = 'orchestrator.adapters.outbound.studios.http_studio_gateway'

class _Resp:
    headers = {}
    status = 200

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, *_size) -> bytes:
        return self._body

    def __enter__(self) -> '_Resp':
        return self

    def __exit__(self, *args: object) -> bool:
        return False

def _http_error(status: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError('http://test', status, 'refused', None, io.BytesIO(json.dumps(body).encode()))

def _rest_gateway(monkeypatch, reply):
    """A gateway whose REST door answers (or raises) ``reply``; requests recorded."""
    gateway = HttpStudioGateway(config=None, domain='test.example')
    requests: list = []

    def fake_urlopen(req, timeout=None):
        requests.append(req)
        if isinstance(reply, Exception):
            raise reply
        return _Resp(json.dumps(reply).encode())
    monkeypatch.setattr(f'{_MODULE}.urllib.request.urlopen', fake_urlopen)
    return (gateway, requests)

def _mcp_forbidden(monkeypatch, gateway):

    def _fail(*args, **kwargs):
        raise AssertionError('the MCP door must not be used here')
    monkeypatch.setattr(gateway, '_tool', _fail)

@intent('INT-FC-R118')
def test_the_fleet_read_rides_the_internal_rest_door(monkeypatch):
    gateway, requests = _rest_gateway(monkeypatch, [{'name': 'gamma-app'}])
    _mcp_forbidden(monkeypatch, gateway)
    assert gateway.platform_apps() == [PlatformApp('gamma-app', 'gamma-app')]
    assert requests[0].full_url == 'http://platform-studio.platform-studio.svc.cluster.local:8001/api/apps'

@intent('INT-FC-R118')
def test_the_scaffold_write_posts_its_body_over_rest(monkeypatch):
    gateway, requests = _rest_gateway(monkeypatch, {'name': 'gamma-app', 'repo_url': 'https://example/gamma-app'})
    _mcp_forbidden(monkeypatch, gateway)
    out = gateway.create_app_repo('gamma-app', 'Gamma App', 'A delivery')
    assert out is None
    req = requests[0]
    assert req.full_url.endswith(':8001/api/repos/app')
    assert req.get_method() == 'POST'
    assert json.loads(req.data) == {'name': 'gamma-app', 'repo': '', 'display_name': 'Gamma App', 'description': 'A delivery'}

@intent('INT-FC-R177')
def test_the_scaffold_write_waits_for_the_studio_and_reads_keep_the_short_timeout(monkeypatch):
    """The scaffold is a write the studio performs in the request (about ten seconds of GitHub
    calls); the read timeout cut it off partway and left a scaffolded repository with no line.
    It waits longer than a read, and less than the execution door's proxy waits for the
    whole establish."""
    gateway = HttpStudioGateway(config=None, domain='test.example')
    calls: list = []

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url.rsplit(':8001', 1)[-1], timeout))
        return _Resp(json.dumps([] if req.get_method() == 'GET' else {'name': 'gamma-app'}).encode())
    monkeypatch.setattr(f'{_MODULE}.urllib.request.urlopen', fake_urlopen)
    gateway.create_app_repo('gamma-app', 'Gamma App', 'A delivery')
    gateway.platform_apps()
    (create_path, create_timeout), (read_path, read_timeout) = calls
    assert (create_path, read_path) == ('/api/repos/app', '/api/apps')
    assert read_timeout == 8
    door = (Path(__file__).resolve().parents[1] / 'devops' / 'web.conf.template').read_text().split(':8081;', 1)[1]
    door_limit = int(re.search(r'proxy_read_timeout (\d+)s;', door).group(1))
    assert 30 <= create_timeout < door_limit

@intent('INT-FC-R118')
def test_a_typed_refusal_carries_the_class_and_never_falls_back(monkeypatch):
    gateway, _ = _rest_gateway(monkeypatch, _http_error(409, {'error': 'AlreadyExistsError', 'detail': 'repository gamma-app'}))
    _mcp_forbidden(monkeypatch, gateway)
    with pytest.raises(StudioToolError) as caught:
        gateway.create_app_repo('gamma-app', 'Gamma App', 'A delivery')
    assert caught.value.error == 'AlreadyExistsError'
    assert 'gamma-app' in caught.value.detail

@intent('INT-FC-R118')
def test_a_502_write_failure_is_typed_too(monkeypatch):
    gateway, _ = _rest_gateway(monkeypatch, _http_error(502, {'error': 'PrFailedError', 'detail': 'push rejected'}))
    _mcp_forbidden(monkeypatch, gateway)
    with pytest.raises(StudioToolError) as caught:
        gateway.pause_app('gamma-app')
    assert caught.value.error == 'PrFailedError'

@intent('INT-FC-R118')
@pytest.mark.parametrize('act', ['pause', 'resume', 'scaffold'])
def test_a_transport_failure_is_unavailable_after_one_rest_attempt(monkeypatch, act):
    gateway, requests = _rest_gateway(monkeypatch, urllib.error.URLError(ConnectionRefusedError('unavailable')))
    _mcp_forbidden(monkeypatch, gateway)
    with pytest.raises(SourceUnavailable):
        if act == 'pause':
            gateway.pause_app('gamma-app')
        elif act == 'resume':
            gateway.resume_app('gamma-app')
        else:
            gateway.create_app_repo('gamma-app', 'Gamma App', 'A delivery')
    assert len(requests) == 1


@intent('INT-FC-R118')
def test_unavailable_platform_inventory_reports_source_failure(monkeypatch):
    gateway, requests = _rest_gateway(monkeypatch, urllib.error.URLError(ConnectionRefusedError('down')))
    _mcp_forbidden(monkeypatch, gateway)
    with pytest.raises(SourceUnavailable):
        gateway.platform_apps()
    assert len(requests) == 1


def test_platform_inventory_normalizes_explicit_repository_url(monkeypatch):
    gateway, _ = _rest_gateway(monkeypatch, [{"name": "portal", "manifest": {"repo_url": "https://github.com/foreign/app.git", "hostname": "app.example", "revision": "abc"}, "status": "running"}])
    assert gateway.platform_apps() == [PlatformApp("portal", "foreign/app", True, "running", "app.example", "abc")]


def test_malformed_explicit_repository_is_not_a_default(monkeypatch):
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
    gateway, _ = _rest_gateway(monkeypatch, [{"name": "portal", "repo": "bad/repo/extra"}])
    with pytest.raises(SourceUnavailable, match="repository declaration"):
        gateway.platform_apps()


def test_declared_slug_uses_the_repository_url_owner(monkeypatch):
    gateway, _ = _rest_gateway(monkeypatch, [{"name": "portal", "repo": "app", "manifest": {"repo_url": "https://github.com/foreign/app.git"}}])
    assert gateway.platform_apps()[0].repository == "foreign/app"


def test_a_repository_reported_as_the_app_name_yields_to_the_deployed_source(monkeypatch):
    gateway, _ = _rest_gateway(monkeypatch, [{"name": "access", "repo": "access", "manifest": {"repo_url": "https://github.com/org/access-psaeng"}}])
    assert gateway.platform_apps()[0].repository == "org/access-psaeng"


def test_conflicting_repository_declarations_are_unavailable(monkeypatch):
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
    gateway, _ = _rest_gateway(monkeypatch, [{"name": "portal", "repo": "owner/app", "manifest": {"repo_url": "https://github.com/foreign/app.git"}}])
    with pytest.raises(SourceUnavailable, match="disagree"):
        gateway.platform_apps()


def test_lifecycle_refused_state_is_not_published_as_paused(monkeypatch):
    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
    gateway, requests = _rest_gateway(monkeypatch, {"name": "gamma-app", "paused": False})
    with pytest.raises(SourceUnavailable, match="acknowledgement"):
        gateway.pause_app("gamma-app")
    assert len(requests) == 1


@pytest.mark.parametrize('inventory', ['platform_apps', 'estimatekit_slugs', 'protopane_slugs'])
@pytest.mark.parametrize('primed', [False, True])
@intent('INT-FC-R144', 'INT-FC-R147')
def test_studio_inventory_outage_preserves_fleet_truth_and_marks_freshness(monkeypatch, inventory, primed):
    from capability_support import make_capabilities
    from test_fleet import FakeRepos, FakeSource, FakeGateway

    studios = FakeGateway()
    service = make_capabilities(FakeRepos(), source=FakeSource(), studios=studios)
    if primed:
        service.refresh.execute()
    observations = service.refresh.observations
    prior = list(observations.fleet)
    prior_time = (service.snapshot_metadata.execute().get('freshness') or {}).get('observed_at')
    actual = HttpStudioGateway(config=None)
    def unavailable(*args, **kwargs):
        raise SourceUnavailable('studio inventory unavailable')
    monkeypatch.setattr(actual, '_rest', unavailable)
    monkeypatch.setattr(actual, '_tool', unavailable)
    monkeypatch.setattr(studios, inventory, getattr(actual, inventory))
    service.refresh.execute()
    assert observations.fleet == prior
    if primed:
        assert next(item for item in observations.fleet if item.name == 'shipped').onboarded
    freshness = service.snapshot_metadata.execute()['freshness']
    assert freshness['state'] == ('stale' if primed else 'unavailable')
    assert freshness['reason_code'] == 'source_unavailable'
    assert freshness['observed_at'] == prior_time


@pytest.mark.parametrize('reply', [None, [], {}, {'projects': None}, {'projects': [None]}, {'projects': ['']}])
def test_malformed_estimation_inventory_is_unavailable(monkeypatch, reply):
    gateway = HttpStudioGateway(config=None)
    monkeypatch.setattr(gateway, '_tool', lambda *a: reply)
    with pytest.raises(SourceUnavailable):
        gateway.estimatekit_slugs()


@pytest.mark.parametrize('reply', [None, {}, [{'name': 'missing-slug'}], [{'slug': None}], [{'slug': 17}], [{'slug': ''}]])
def test_malformed_prototype_inventory_is_unavailable(monkeypatch, reply):
    gateway = HttpStudioGateway(config=None)
    monkeypatch.setattr(gateway, '_tool', lambda *a: reply)
    with pytest.raises(SourceUnavailable):
        gateway.protopane_slugs()


def test_successful_empty_studio_inventories_are_empty_truth(monkeypatch):
    gateway = HttpStudioGateway(config=None)
    monkeypatch.setattr(gateway, '_rest', lambda *a: [])
    monkeypatch.setattr(gateway, '_tool', lambda studio, *a: {'projects': []} if studio == 'estimatekit' else [])
    assert gateway.platform_apps() == []
    assert gateway.estimatekit_slugs() == gateway.protopane_slugs() == set()
