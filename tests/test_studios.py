"""The connective cross-studio view: per delivery, what exists in each studio
(estimatekit project, protopane prototype, platform app), and the org-wide studio
reachability. Cached off the read path, degrading when a studio is down. Audit with
`csd-intent .`."""
from capability_support import with_lifecycle
from pytest_intent import intent
from orchestrator.adapters.inbound.http.mappers.delivery import overview_dto
from orchestrator.adapters.inbound.http.mappers.studios import studios_dto
from capability_support import make_capabilities
from orchestrator.adapters.outbound.memory.studios_index import StudioStatusIndex
from orchestrator.domain.model.studio_artifact import StudioArtifact
from orchestrator.domain.model.studio_health import StudioHealth

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

class FakeGateway:

    def __init__(self):
        self.slugs_seen = []

    def health(self):
        return [StudioHealth('estimatekit', True, 'ok', 'https://estimatekit.x'), StudioHealth('protopane', False, 'unreachable', 'https://protopane.x')]

    def artifacts_for(self, slug):
        self.slugs_seen.append(slug)
        return {'proposal': StudioArtifact('estimatekit', True, True, f'https://estimatekit.x/projects/{slug}/slides/', 'estimation project'), 'design': StudioArtifact('protopane', True, False, 'https://protopane.x', 'no prototype'), 'build': StudioArtifact('platform-studio', False, None, 'https://platform-studio.x', 'unreachable')}

@intent('INT-FC-R34')
def test_studio_status_is_cached_off_the_read_path():
    gw = FakeGateway()
    idx = StudioStatusIndex()
    assert idx.health() == []
    assert idx.artifacts('acme') == {}
    assert gw.slugs_seen == []
    idx.refresh(gw, ['acme'])
    assert [h.studio for h in idx.health()] == ['estimatekit', 'protopane']
    assert idx.artifacts('acme')['proposal'].exists is True
    assert gw.slugs_seen == ['acme']

@intent('INT-FC-R35')
def test_delivery_overview_maps_studio_artifacts_onto_the_phase_line(tmp_path):
    gw = FakeGateway()
    idx = StudioStatusIndex()
    idx.refresh(gw, ['acme'])
    service = make_capabilities(FakeRepos(), studios=gw, studio_index=idx)
    dto = overview_dto(service.delivery_overview.execute(str(tmp_path / 'acme')))
    phases = {p['name']: p for p in dto['phases']}
    assert phases['scope']['question'] == 'What is asked, and what would it cost?'
    assert phases['scope']['studio'] == 'estimatekit'
    assert phases['scope']['artifact']['exists'] is True
    assert 'acme' in phases['scope']['artifact']['url']
    assert phases['intent+plan']['studio'] is None
    assert phases['intent+plan']['artifact'] is None

@intent('INT-FC-R36')
def test_studios_view_reports_per_studio_reachability():
    gw = FakeGateway()
    idx = StudioStatusIndex()
    idx.refresh(gw, [])
    service = make_capabilities(FakeRepos(), studios=gw, studio_index=idx)
    by = {s['studio']: s for s in studios_dto(service.studios.execute())['studios']}
    assert by['estimatekit']['reachable'] is True
    assert by['protopane']['reachable'] is False
