"""Each phase worker is a named playbook catalog agent (issue #62). The Console binds every
step it runs to one of the catalog's people - the five phase workers, the fresh-eyes
Reviewer, the Programmer, the Release Manager - reads that agent's posture and character
from the playbook studio at launch, keys the step's git identity on the agent, and surfaces
who ran each step in the compiled Workflow, the run rows, the node graph, and the pod log.
A catalog that cannot be read degrades to the anonymous worker of before, recorded in the
orchestrator's log, never a failed run. Audit: csd-intent ."""
from capability_support import invoke_helper
from capability_support import command_kwargs
import logging
from dataclasses import replace
from pathlib import Path
from pytest_intent import intent
from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
from orchestrator.adapters.outbound.argo.argo_workflow_runner import parse_graph, parse_runs
from orchestrator.domain.services.maintenance_launch import ACT_AGENTS
from orchestrator.adapters.outbound.argo.maintenance_launch import compile_maintenance_workflow
from orchestrator.domain.services.promotion_launch import PROMOTE_AGENT
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from capability_support import make_capabilities
from orchestrator.adapters.outbound.argo.worker_template import AGENT_EDITING_TOOLS
from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.domain.model.catalog_agent import CatalogAgent
from orchestrator.domain.catalog import agent_title, parse_catalog_agent
from orchestrator.domain.delivery import LEARN, REVIEW_AGENT, SEQUENCE
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
_ROSTER = {'architect': ('Architect', 'auto', True, False), 'designer': ('Designer', 'auto', True, False), 'planner': ('Planner', 'auto', True, False), 'builder': ('Builder', 'auto', True, False), 'librarian': ('Librarian', 'auto', True, False), 'reviewer': ('Reviewer', 'plan', False, True), 'programmer': ('Programmer', 'auto', True, False), 'release-manager': ('Release Manager', 'auto', True, False)}

def _catalog() -> dict[str, CatalogAgent]:
    return {name: CatalogAgent(name=name, title=title, description=f'{title} work; hand it {name} work.', skills=('some-skill',), doors=(), permission=permission, writes=writes, fresh_eyes=fresh, body=f'You are the {title}. You refuse what the {title} refuses.') for name, (title, permission, writes, fresh) in _ROSTER.items()}

def _fresh_state(tmp_path):
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    return replace(derive_state(str(tmp_path / 'acme')), scratch_ref='delivery/2026-08-22')

def _workers(wf) -> dict[str, dict]:
    return {t['name']: t for t in wf['spec']['templates'] if 'container' in t}

def _env(template) -> dict[str, dict]:
    return {e['name']: e for e in template['container']['env']}

class FakeRepos:

    def list_delivery_repos(self):
        return []

class CatalogStudios:

    def __init__(self, roster=None, fail=False):
        self._roster = roster
        self._fail = fail
        self.reads = 0

    def agent_catalog(self):
        self.reads += 1
        if self._fail:
            from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
            raise SourceUnavailable('playbook-studio unreachable')
        return list((self._roster or {}).values())

    def health(self):
        return []

@intent('INT-FC-R138')
def test_every_delivery_phase_is_bound_to_a_catalog_agent_and_the_workflow_carries_it(tmp_path):
    wf = compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=_catalog())
    workers = _workers(wf)
    assert len(workers) == len(SEQUENCE)
    for phase in SEQUENCE:
        assert phase.agent, f'{phase.name} names nobody'
        worker = workers[f"worker-{phase.name.replace('+', '-')}"]
        env = _env(worker)
        assert env['FC_AGENT']['value'] == phase.agent
        assert worker['metadata']['labels']['foundry-console/agent'] == phase.agent
        assert env['FC_AGENT_TITLE']['value'] == _ROSTER[phase.agent][0]
    assert {p.agent for p in (*SEQUENCE, LEARN)} == {'architect', 'designer', 'planner', 'builder', 'librarian'}
    assert REVIEW_AGENT == 'reviewer' and REVIEW_AGENT not in {p.agent for p in (*SEQUENCE, LEARN)}

@intent('INT-FC-R138')
def test_delivery_steps_bind_no_reviewer_because_the_gate_review_is_the_phases(tmp_path):
    wf = compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=_catalog())
    for phase in SEQUENCE:
        env = _env(_workers(wf)[f"worker-{phase.name.replace('+', '-')}"])
        assert not [k for k in env if k.startswith('FC_REVIEWER')]

@intent('INT-FC-R138')
def test_maintenance_and_promotion_steps_are_bound_too():
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)
    wf = compile_maintenance_workflow('org/app', 'resolve', 7, MaintenanceMode.ONE_SHOT, cfg, run_id='m1', catalog=_catalog())
    workers = _workers(wf)
    assert _env(workers['worker-resolve'])['FC_AGENT']['value'] == ACT_AGENTS['resolve'] == 'programmer'
    assert _env(workers['worker-review'])['FC_AGENT']['value'] == ACT_AGENTS['review'] == 'reviewer'
    assert ACT_AGENTS['reconcile-docs'] == 'programmer'
    assert PROMOTE_AGENT == 'release-manager'

@intent('INT-FC-R139')
def test_posture_and_character_ride_from_the_catalog_entry(tmp_path):
    wf = compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=_catalog())
    env = _env(_workers(wf)['worker-build-ship'])
    assert env['FC_AGENT_PERMISSION']['value'] == 'auto'
    assert env['FC_AGENT_WRITES']['value'] == 'true'
    assert env['FC_AGENT_PROMPT']['value'].startswith('You are the Builder.')
    for key in ('FC_AGENT', 'FC_AGENT_TITLE', 'FC_AGENT_PERMISSION', 'FC_AGENT_WRITES', 'FC_AGENT_PROMPT'):
        assert 'value' in env[key] and 'valueFrom' not in env[key]

@intent('INT-FC-R139')
def test_an_unreadable_catalog_degrades_to_the_named_but_anonymous_worker(tmp_path):
    named = compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=None)
    env = _env(_workers(named)['worker-scope'])
    assert env['FC_AGENT']['value'] == 'architect'
    assert env['FC_AGENT_TITLE']['value'] == agent_title('architect') == 'Architect'
    assert not {k for k in env if k.startswith('FC_AGENT_')} - {'FC_AGENT_TITLE'}
    assert not [k for k in env if k.startswith('FC_REVIEWER')]
    full = _env(_workers(compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=_catalog()))['worker-scope'])
    skip = {k for k in full if k.startswith(('FC_AGENT', 'FC_REVIEWER'))}
    assert {k: v for k, v in full.items() if k not in skip} == {k: v for k, v in env.items() if k not in skip}

@intent('INT-FC-R139')
def test_the_service_reads_the_catalog_once_per_drive_and_logs_a_degradation(caplog):
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), studios=CatalogStudios(_catalog()))
    assert set(invoke_helper(svc, '_agent_catalog')) == set(_ROSTER)
    down = CatalogStudios(fail=True)
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), studios=down)
    with caplog.at_level(logging.WARNING, logger='orchestrator.application.services.definitions'):
        assert invoke_helper(svc, '_agent_catalog') == {}
    assert any(('agent catalog unreachable' in r.getMessage() for r in caplog.records))
    assert down.reads == 1
    empty = CatalogStudios(roster={})
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), studios=empty)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger='orchestrator.application.services.definitions'):
        assert invoke_helper(svc, '_agent_catalog') == {}
    assert any(('empty or unreachable' in r.getMessage() for r in caplog.records))

@intent('INT-FC-R139')
def test_the_catalog_entry_is_parsed_from_the_studio_wire_shape():
    raw = {'name': 'reviewer', 'title': 'Reviewer', 'galaxy': 'craft', 'description': 'Reviews with fresh eyes; hand it a pull request.', 'refs': ['REF-Delivery'], 'skills': ['adversarial-review', 'review-pr'], 'doors': [], 'posture': {'permission': 'plan', 'writes': False, 'fresh_eyes': True}, 'appearance': None, 'summary': 'Reviews with fresh eyes; hand it a pull request.', 'raw': '---\n...', 'body': '# Agent: Reviewer\n\nYou are the Reviewer.'}
    agent = parse_catalog_agent(raw)
    assert agent == CatalogAgent('reviewer', 'Reviewer', 'Reviews with fresh eyes; hand it a pull request.', ('adversarial-review', 'review-pr'), (), 'plan', False, True, '# Agent: Reviewer\n\nYou are the Reviewer.')
    assert parse_catalog_agent({'title': 'nobody'}) is None
    assert parse_catalog_agent('not a row') is None

@intent('INT-FC-R140')
def test_the_git_identity_is_keyed_on_the_agent_wherever_that_agent_works(tmp_path):
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore())
    svc.set_git_identity.execute('Foundry Build', 'b@x', 'foundry-build-bot', 'pat-B', **command_kwargs(''))
    svc.set_git_identity.execute('Foundry Maint', 'm@x', 'foundry-maint-bot', 'pat-M', **command_kwargs(''))
    svc.set_git_roles.execute({'builder': 'Foundry Build', 'programmer': 'Foundry Maint'}, **command_kwargs(''))
    identities = invoke_helper(svc, '_git_identities_map')
    assert set(identities) == {'builder', 'programmer'}
    wf = compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', git_identities=identities)
    workers = _workers(wf)
    assert _env(workers['worker-build-ship'])['FC_GIT_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-gitid-foundry-build-key'
    assert 'FC_GIT_TOKEN' not in _env(workers['worker-scope'])
    cfg = RunConfig(worker_credential='tok', repo_target='org/app', repo_rights=True)
    for act in ('resolve', 'reconcile-docs'):
        mw = compile_maintenance_workflow('org/app', act, 7, MaintenanceMode.GATED, cfg, run_id='m1', git_identities=identities)
        step = _env(_workers(mw)[f'worker-{act}'])
        assert step['FC_GIT_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'fc-gitid-foundry-maint-key'

@intent('INT-FC-R140')
def test_the_settings_grid_lists_the_catalog_agents_not_the_steps():
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore())
    catalog = svc.git_role_catalog.execute()
    keys = [r['key'] for r in catalog]
    assert keys == ['architect', 'designer', 'planner', 'builder', 'librarian', 'programmer', 'reviewer', 'release-manager', 'console']
    by_key = {r['key']: r for r in catalog}
    assert by_key['programmer']['label'].startswith('Programmer: ') and 'reconcile-docs' in by_key['programmer']['label']
    assert by_key['reviewer']['label'].startswith('Reviewer: ') and 'maintenance: review' in by_key['reviewer']['label']
    assert by_key['release-manager']['label'].startswith('Release Manager: ')
    svc.set_git_identity.execute('Foundry Build', 'b@x', 'foundry-build-bot', 'pat-B', **command_kwargs(''))
    assert svc.set_git_roles.execute({'build-ship': 'Foundry Build', 'builder': 'Foundry Build'}, **command_kwargs('')) == {'builder': 'Foundry Build'}

def _argo_item():
    return {'metadata': {'name': 'delivery-acme-abc12', 'labels': {'foundry-console/run': 'r1', 'foundry-console/mode': 'one-shot'}}, 'spec': {'templates': [{'name': 'line', 'steps': []}, {'name': 'worker-scope', 'metadata': {'labels': {'foundry-console/run': 'r1', 'foundry-console/phase': 'scope', 'foundry-console/agent': 'architect'}}, 'container': {}}, {'name': 'worker-design', 'metadata': {'labels': {'foundry-console/run': 'r1', 'foundry-console/phase': 'design', 'foundry-console/agent': 'designer'}}, 'container': {}}, {'name': 'gate-proposal', 'suspend': {}}]}, 'status': {'phase': 'Running', 'nodes': {'n1': {'id': 'n1', 'name': 'scope', 'type': 'Pod', 'phase': 'Succeeded', 'templateName': 'worker-scope'}, 'n2': {'id': 'n2', 'name': 'gate-proposal', 'type': 'Suspend', 'phase': 'Running', 'templateName': 'gate-proposal'}, 'n3': {'id': 'n3', 'name': 'design', 'type': 'Pod', 'phase': 'Pending', 'templateName': 'worker-design'}}}}

@intent('INT-FC-R141')
def test_run_rows_and_graph_nodes_read_the_agent_off_the_workflow_object():
    row = parse_runs({'items': [_argo_item()]})[0]
    assert row.agents == ('architect', 'designer')
    graph = parse_graph(_argo_item())
    by_name = {n.name: n for n in graph.nodes}
    assert by_name['scope'].agent == 'architect'
    assert by_name['design'].agent == 'designer'
    assert by_name['gate-proposal'].agent is None
    bare = _argo_item()
    for t in bare['spec']['templates']:
        t.get('metadata', {}).get('labels', {}).pop('foundry-console/agent', None)
    assert parse_runs({'items': [bare]})[0].agents == ()

@intent('INT-FC-R141')
def test_the_entrypoint_announces_the_agent_and_runs_under_its_paragraph():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert 'echo "worker: ${FC_PHASE} runs as ${FC_AGENT}' in entrypoint
    assert 'FC_REVIEWER' not in entrypoint
    assert 'agent_flags+=(--append-system-prompt "$FC_AGENT_PROMPT")' in entrypoint
    assert f'--disallowedTools "{AGENT_EDITING_TOOLS}"' in entrypoint
    assert entrypoint.count('--disallowedTools') == 1
    assert '"${agent_flags[@]}"' in entrypoint
    assert 'runs unnamed (no catalog agent bound)' in entrypoint

@intent('INT-FC-R151')
def test_a_tooled_gates_worker_carries_the_studios_east_west_url_and_the_slug(tmp_path):
    urls = {'estimatekit': 'http://estimatekit.estimatekit.svc:8001', 'protopane': 'http://protopane.protopane.svc:8801'}
    wf = compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=_catalog(), tool_urls=urls)
    workers = _workers(wf)
    for phase in SEQUENCE:
        env = _env(workers[f"worker-{phase.name.replace('+', '-')}"])
        assert env['FC_SLUG']['value'] == 'acme'
        assert env['FC_TOOL_URL']['value'] == urls.get(phase.studio, '')
    assert _env(workers['worker-scope'])['FC_TOOL_URL']['value'] == urls['estimatekit']
    assert _env(workers['worker-design'])['FC_TOOL_URL']['value'] == urls['protopane']
    assert _env(workers['worker-intent-plan'])['FC_TOOL_URL']['value'] == ''
    assert _env(workers['worker-build-ship'])['FC_TOOL_URL']['value'] == ''
    bare = _env(_workers(compile_workflow('acme', _fresh_state(tmp_path), RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1', catalog=_catalog()))['worker-scope'])
    assert bare['FC_TOOL_URL']['value'] == '' and bare['FC_SLUG']['value'] == 'acme'

@intent('INT-FC-R151')
def test_the_service_reads_the_export_doors_off_the_studio_port():
    from orchestrator.adapters.outbound.studios.http_studio_gateway import HttpStudioGateway, internal_base_url

    class Doors:

        def tool_url(self, studio):
            return {'estimatekit': 'http://ek:8001', 'protopane': 'http://pp:8801'}.get(studio, '')
    svc = make_capabilities(FakeRepos(), config=InMemoryConfigStore(), studios=Doors())
    assert svc.tool_urls.execute(CURRENT_LIFECYCLE) == {'estimatekit': 'http://ek:8001', 'protopane': 'http://pp:8801'}
    assert make_capabilities(FakeRepos(), config=InMemoryConfigStore(), studios=object()).tool_urls.execute(CURRENT_LIFECYCLE) == {}
    assert make_capabilities(FakeRepos(), config=InMemoryConfigStore()).tool_urls.execute(CURRENT_LIFECYCLE) == {}
    gw = HttpStudioGateway(config=None, domain='test.example')
    assert gw.tool_url('estimatekit') == internal_base_url('estimatekit', gw._svc)
    assert gw.tool_url('protopane') == internal_base_url('protopane', gw._svc)
    assert gw.tool_url('nowhere') == ''
