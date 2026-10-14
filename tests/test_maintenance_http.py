from orchestrator.domain.model.repository_inventory_entry import RepositoryInventoryEntry
from delivery_fixtures import record_inputs
from maintenance_fixtures import semantic_issue, semantic_pr
from capability_support import observe_repo
"""The maintenance door over HTTP (INT-FC-R62) and the standing negatives
(INT-FC-R69): no /mcp, no Projects API, no maintenance state file."""
from pathlib import Path
from fastapi.testclient import TestClient
from pytest_intent import intent
from orchestrator.adapters.inbound.http.app import create_app
from capability_support import make_capabilities
from orchestrator.domain.services.delivery_resolution import derive_from_records
from tests.test_maintenance_service import FakeActs, FakeConfig, FakeCredentials, FakeMSource, FakeRepos, FakeWorkflows, _pr

class RecordingMSource(FakeMSource):
    """Every GitHub path the source is asked for, recorded - the R69 negative needs to
    prove no Projects API is behind the maintenance surface."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls: list[str] = []

    def open_issues(self, repo):
        self.calls.append('issues')
        return tuple(semantic_issue(record) for record in ([{'number': 7, 'title': 'broken link', 'user': {'login': 'rafael'}, 'labels': [{'name': 'docs'}], 'html_url': 'http://x/7'}]))

    def open_prs(self, repo):
        self.calls.append('pulls')
        return tuple(semantic_pr(record) for record in (super().open_prs(repo)))

class MidDeliverySource:
    """A delivery source whose one repo is MID-DELIVERY (scope committed, unsigned):
    maintenance must answer for it all the same (an always-on mode, not a graduation)."""

    def scan(self):
        return [derive_from_records('org/app', True, record_inputs({'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n'}))]

    def state_of(self, repo):
        return derive_from_records(repo, True, record_inputs({'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n'}))

    def read_config(self, repo, *, revision=""):
        return {}

    def present_records(self, repo):
        return ['proposal.md']

    def list_org_repos(self):
        return [RepositoryInventoryEntry(repository='org/app', name='app', updated_at=None, topics=(), repository_id='')]

def _client(msource, acts=None, workflows=None):
    svc = make_capabilities(FakeRepos(), workflows=workflows or FakeWorkflows(), credentials=FakeCredentials(), config=FakeConfig(), source=MidDeliverySource(), msource=msource, macts=acts or FakeActs())
    svc.refresh.execute()
    observe_repo(svc, 'org/app')
    return (TestClient(create_app(svc)), svc)

@intent('INT-FC-R62')
def test_state_serves_three_concerns_for_a_mid_delivery_repo():
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [{'user': {'login': 'reviewer'}, 'body': 'ok\nVERDICT: PASS', 'submitted_at': 't', 'author_association': 'MEMBER', 'state': 'APPROVED'}]}
    files = {12: [{'filename': 'a.py', 'status': 'modified', 'additions': 1, 'deletions': 0, 'patch': '+x'}]}
    client, _ = _client(RecordingMSource(prs=[_pr(12)], reviews=passing, checks={'abc': green}, files=files))
    body = client.get('/api/maintenance/state', params={'repo': 'org/app'}).json()
    assert 'train' in body['positions'] and 'prs' in body['positions'] and ('issues' in body['positions'])
    assert body['positions']['prs'][0]['verdict'] == 'pass'
    assert body['action']['default_mode'] == 'gated'
    assert set(body['action']['acts']) == {'resolve', 'review', 'reconcile-docs'}
    assert set(body['action']['modes']) == {'gated', 'one-shot', 'direct'}
    assert body['delivery']['status'] == 'awaiting-gate'
    pr = client.get('/api/maintenance/substance', params={'repo': 'org/app', 'kind': 'pr', 'id': 12}).json()
    assert pr['files'][0]['patch'] == '+x'
    issue = client.get('/api/maintenance/substance', params={'repo': 'org/app', 'kind': 'issue', 'id': 7}).json()
    assert issue['kind'] == 'issue'
    inbox = client.get('/api/maintenance/inbox').json()
    assert 'items' in inbox

@intent('INT-FC-R176')
def test_drive_route_works_without_an_inline_credential():
    """The pane's actual request shape (maintenance.actions.ts): config carries no
    credential and asserts no write right; the repo's persisted agent backs the worker and
    the right is the drive's own. The route must 200, not 422 - the 6.18.0 regression was
    exactly this body refused with 'repository target and write rights are required'."""
    svc = make_capabilities(FakeRepos(), workflows=FakeWorkflows(), credentials=FakeCredentials(persisted=True), config=FakeConfig(), source=MidDeliverySource(), msource=RecordingMSource(prs=[_pr(12)]), macts=FakeActs())
    client = TestClient(create_app(svc))
    r = client.post('/api/maintenance/drive', json={'repo': 'org/app', 'act': 'resolve', 'target': 7, 'mode': 'gated', 'config': {'worker_credential': None, 'repo_target': 'org/app'}})
    assert r.status_code == 200 and r.json()['handle']
    bad = client.post('/api/maintenance/drive', json={'repo': 'org/app', 'act': 'resolve', 'target': 7, 'mode': 'yolo', 'config': {}})
    assert bad.status_code == 422

@intent('INT-FC-R69')
def test_no_mcp_no_projects_api_no_maintenance_state_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = RecordingMSource(prs=[_pr(12)])
    client, svc = _client(src)
    assert client.get('/mcp').status_code == 404
    assert client.post('/mcp/', json={}).status_code == 404
    assert client.get('/api/mcp').status_code == 404
    client.get('/api/maintenance/state', params={'repo': 'org/app'})
    client.get('/api/maintenance/substance', params={'repo': 'org/app', 'kind': 'pr', 'id': 12})
    client.get('/api/maintenance/substance', params={'repo': 'org/app', 'kind': 'docs'})
    client.get('/api/maintenance/inbox')
    svc.refresh.execute()
    assert all(('project' not in c for c in src.calls))
    assert not (tmp_path / '.maintenance').exists()
    assert list(tmp_path.rglob('*.json')) == []
    import orchestrator.adapters.outbound.github.github_maintenance_source as gm
    import orchestrator.adapters.outbound.github.github_acts as ga
    for mod in (gm, ga):
        text = Path(mod.__file__).read_text(encoding='utf-8')
        assert '/projects' not in text
