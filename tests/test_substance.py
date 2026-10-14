from orchestrator.domain.model.repository_file import RepositoryFile
"""The cockpit's phase substance rides the studios' own REST east-west (the internal
Service port) and degrades to {} - the UI then falls back to the phase's committed
record. MCP stays the agents' door. Audit: csd-intent ."""

from capability_support import make_capabilities
from pytest_intent import intent

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


class FakeRepos:

    def list_delivery_repos(self):
        return []

class FakeStudios:

    def __init__(self):
        self.calls = []

    def scope_substance(self, slug, *, studio):
        self.calls.append(('scope', slug))
        return {'summary': {'name': 'Acme', 'requirement_count': 3}}

    def design_substance(self, slug, *, studio):
        self.calls.append(('design', slug))
        return {'theme_css': ':root{--primary:1}', 'screens': [{'slug': 'home'}]}

@intent('INT-FC-R53')
def test_phase_substance_routes_by_phase_and_degrades_to_empty():
    studios = FakeStudios()
    svc = make_capabilities(FakeRepos(), studios=studios)
    assert svc.phase_substance.execute('example-org/acme', 'scope')['summary']['requirement_count'] == 3
    assert svc.phase_substance.execute('example-org/acme', 'design')['theme_css'] == ':root{--primary:1}'
    assert studios.calls == [('scope', 'acme'), ('design', 'acme')]
    assert svc.phase_substance.execute('example-org/acme', 'intent+plan') == {}
    assert make_capabilities(FakeRepos()).phase_substance.execute('example-org/acme', 'scope') == {}

    class Down(FakeStudios):

        def scope_substance(self, slug, *, studio):
            from orchestrator.domain.exceptions.source_unavailable import (
                SourceUnavailable,
            )
            raise SourceUnavailable('studio unreachable')
    import pytest

    from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
    with pytest.raises(SourceUnavailable):
        make_capabilities(FakeRepos(), studios=Down()).phase_substance.execute('a/b', 'scope')

def test_intent_plan_folds_yaml_block_scalars_into_claim_statements():
    """intent.yaml authors statements as YAML block scalars ('>-' folded, '|' literal); the
    claims table must fold them into real text and never leak the raw '>-' indicator. Inline
    one-line statements pass through unchanged. Regression: every multi-line claim (the common
    CSD authoring style) rendered as a bare '>-' in the pane."""
    intent_yaml = 'INT-GEN-001:\n  status: draft\n  criticality: critical\n  statement: >-\n    Each generated sentence is composed from four word banks;\n    the phrase is prefixed only on the first sentence.\nINT-UI-E01:\n  status: draft\n  criticality: medium\n  statement: The page displays a "Falar Sem Dizer Nada" banner.\nINT-UI-E02:\n  status: draft\n  criticality: high\n  statement: |\n    line one\n    line two\n'

    class Source:

        def content_revision(self, repo, path=""):
            return "unit-head"

        def file(self, repo, path, *, revision=""):
            return RepositoryFile(path, intent_yaml, len(intent_yaml.encode()))
    svc = make_capabilities(FakeRepos(), source=Source(), studios=FakeStudios())
    by_id = {c['id']: c for c in svc.phase_substance.execute('example-org/acme', 'intent+plan')['claims']}
    assert by_id['INT-GEN-001']['statement'] == 'Each generated sentence is composed from four word banks; the phrase is prefixed only on the first sentence.'
    assert by_id['INT-UI-E01']['statement'] == 'The page displays a "Falar Sem Dizer Nada" banner.'
    assert by_id['INT-UI-E02']['statement'] == 'line one\nline two\n'
    assert all(c['statement'] != '>-' for c in by_id.values())

def test_scope_items_carry_activities_estimate_and_rendered_diagrams(monkeypatch):
    """The scope substance itemizes the activity breakdown with per-phase effort sums, and
    each diagram carries its in-cluster rendered SVG beside the source (source-only when
    the render endpoint is absent)."""
    from orchestrator.adapters.outbound.studios.http_studio_gateway import (
        HttpStudioGateway,
    )
    listing = {'files': [{'name': 'P1-build.tsv', 'path': 'data/activities/P1-build.tsv', 'directory': 'data/activities'}, {'name': 'P2-build.tsv', 'path': 'data/activities/P2-build.tsv', 'directory': 'data/activities'}, {'name': 'P1-overview.puml', 'path': 'data/architecture/P1-overview.puml', 'directory': 'data/architecture', 'kind': 'puml'}]}
    p1 = 'Group\tActivity ID\tActivity\tReq IDs\tEffort (MD)\tDescription\nDesign\tP1-DES-001\tSolution Design\tREQ-1, REQ-2\t3\tspec\nBuild\tP1-BLD-001\tImplement\tREQ-1\t2.5\tcode\n'
    p2 = 'Group\tActivity ID\tActivity\tReq IDs\tEffort (MD)\tDescription\nBuild\tP2-BLD-001\tExtend\tREQ-3\t4\tmore\n'

    def fake_rest(studio, path, method='GET'):
        if path.endswith('/summary'):
            return {'name': 'acme', 'requirement_count': 3}
        if path.endswith('/audit'):
            return {'passed': True, 'passed_count': 5, 'failed_count': 0, 'suggestions': []}
        if path.endswith('/files'):
            return listing
        if path.endswith('/files/data/activities/P1-build.tsv'):
            return {'content': p1}
        if path.endswith('/files/data/activities/P2-build.tsv'):
            return {'content': p2}
        if path.endswith('/files/data/architecture/P1-overview.puml'):
            return {'content': '@startuml\nA --> B\n@enduml'}
        if path.endswith('/architecture/diagrams/P1-overview.puml'):
            return {'name': 'P1-overview.puml', 'svg': "<svg xmlns='x'>ok</svg>"}
        raise SourceUnavailable("optional file absent")
    gw = HttpStudioGateway(config=None)
    monkeypatch.setattr(gw, '_rest', fake_rest)
    out = gw.scope_substance('acme', studio='estimatekit')
    assert len(out['activities']) == 3
    assert out['estimate']['phases'] == [{'id': 'P1', 'effort_md': 5.5}, {'id': 'P2', 'effort_md': 4.0}]
    assert out['estimate']['total_md'] == 9.5
    d = out['architecture']['diagrams'][0]
    assert d['puml'].startswith('@startuml')
    assert d['svg'].startswith('<svg')
