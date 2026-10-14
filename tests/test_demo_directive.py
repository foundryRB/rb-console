from capability_support import with_lifecycle
from orchestrator.domain.model.platform_app import PlatformApp
"""Every worker of a demo line is told it is one (INT-FC-R154): the demo directive rides
every phase's prompt, FC_DEMO_OF rides the pod, an ordinary line carries neither, and
establish defaults a demo's app name to the source app's fleet name under the prefix."""
from capability_support import invoke_helper
from capability_support import command_kwargs
from dataclasses import replace
from pytest_intent import intent
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from capability_support import make_capabilities
from orchestrator.domain.model.demo_source import DemoSource
from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
from orchestrator.adapters.outbound.argo.delivery_workflow import demo_directive
from orchestrator.domain.delivery import SEED_DEMO
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
DEMO = DemoSource(repo='example-org/acme', app='acme-app', demo_app='demo-acme-app')
CFG = RunConfig('tok', 'demo-acme', True, RunMode.INTERACTIVE)

def _state(tmp_path, *, demo_of=''):
    scratch = tmp_path / 'demo-acme' / '.delivery'
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    state = derive_state(str(tmp_path / 'demo-acme'))
    return replace(state, scratch_ref='delivery/2026-09-08', seed=SEED_DEMO if demo_of else state.seed, demo_of=demo_of)

def _workers(workflow):
    return [t for t in workflow['spec']['templates'] if 'container' in t]

@intent('INT-FC-R154')
def test_the_directive_names_the_source_the_fleet_names_and_the_rule():
    text = demo_directive(DEMO, 'example-org/demo-acme')
    for needle in ('DEMO line', 'example-org/acme', '`acme-app`', '`demo-acme-app`', '`demo-acme`', 'demo-line', 'demo_line.py open', 'attest', 'never author'):
        assert needle in text
    assert demo_directive(None, 'example-org/demo-acme') == ''

@intent('INT-FC-R154')
def test_every_phase_of_a_demo_line_carries_the_directive_and_the_env(tmp_path):
    workflow = compile_workflow('example-org/demo-acme', _state(tmp_path, demo_of='example-org/acme'), CFG, run_id='r1', demo=DEMO)
    workers = _workers(workflow)
    assert len(workers) >= 4
    for worker in workers:
        assert 'DEMO line' in worker['container']['args'][0]
        env = {e['name']: e.get('value') for e in worker['container']['env']}
        assert env['FC_DEMO_OF'] == 'example-org/acme'

@intent('INT-FC-R154')
def test_an_ordinary_line_carries_neither(tmp_path):
    workflow = compile_workflow('example-org/acme', _state(tmp_path), CFG, run_id='r1')
    for worker in _workers(workflow):
        assert 'DEMO line' not in worker['container']['args'][0]
        env = {e['name']: e.get('value') for e in worker['container']['env']}
        assert env['FC_DEMO_OF'] == ''

class _Repos:

    def __init__(self):
        self.ensured = []

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        self.ensured.append(target)
        return f'org/{target}'

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class _Studios:
    """A platform-studio whose fleet holds one onboarded app shipping from a prefixed repo."""

    def __init__(self, apps):
        self.apps = apps
        self.calls = []

    def platform_apps(self):
        return self.apps

    def create_app_repo(self, name, display_name, description, repo=''):
        self.calls.append((name, repo))
        return None

@intent('INT-FC-R154')
def test_establish_defaults_a_demo_s_app_name_to_the_source_app_s_fleet_name():
    studios = _Studios([PlatformApp('hello-spa', 'org-hello-spa', onboarded=True, hostname='hello-spa.example')])
    service = make_capabilities(_Repos(), studios=studios)
    service.establish.execute('demo-org-hello-spa', 'Rehearse the line over hello-spa', **command_kwargs('demo-org-hello-spa'))
    assert studios.calls == [('demo-hello-spa', 'demo-org-hello-spa')]

@intent('INT-FC-R154')
def test_establish_keeps_the_default_when_the_source_is_not_onboarded_or_the_name_carries_no_prefix():
    studios = _Studios([])
    service = make_capabilities(_Repos(), studios=studios)
    service.establish.execute('demo-org-hello-spa', 'no source onboarded', **command_kwargs('demo-org-hello-spa'))
    service.establish.execute('org-hello-spa', 'an ordinary line', **command_kwargs('org-hello-spa'))
    assert studios.calls == [('demo-org-hello-spa', 'demo-org-hello-spa'), ('org-hello-spa', 'org-hello-spa')]

@intent('INT-FC-R154')
def test_the_service_reads_the_two_fleet_names_for_the_directive(tmp_path):
    studios = _Studios([PlatformApp('hello-spa', 'org-hello-spa', onboarded=True, hostname=''), PlatformApp('demo-hello-spa', 'demo-org-hello-spa', onboarded=True, hostname='')])
    service = make_capabilities(_Repos(), studios=studios)
    state = _state(tmp_path, demo_of='example-org/org-hello-spa')
    assert invoke_helper(service, '_demo_source', 'example-org/demo-org-hello-spa', state) == DemoSource(repo='example-org/org-hello-spa', app='hello-spa', demo_app='demo-hello-spa')
    only_source = make_capabilities(_Repos(), studios=_Studios([PlatformApp('hello-spa', 'org-hello-spa', onboarded=True, hostname='')]))
    assert invoke_helper(only_source, '_demo_source', 'example-org/demo-org-hello-spa', state).demo_app == 'demo-hello-spa'
    assert invoke_helper(service, '_demo_source', 'example-org/org-hello-spa', _state(tmp_path)) is None
