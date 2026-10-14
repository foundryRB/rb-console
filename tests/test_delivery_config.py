from capability_support import with_lifecycle
from delivery_fixtures import record_header, record_inputs
import json
"""Delivery-level mode governs how a delivery's runs execute, and re-opening a
phase un-signs its gate while leaving downstream records in place for review.
Audit: csd-intent ."""
from capability_support import command_kwargs
from dataclasses import replace
from pathlib import Path
import pytest
from pytest_intent import intent
from orchestrator.adapters.inbound.http.mappers.delivery import overview_dto
from orchestrator.adapters.inbound.http.mappers.config import config_dto
from orchestrator.adapters.outbound.github import github_repo_store as github_store
from orchestrator.adapters.outbound.github.github_repo_store import GitHubRepoStore, _pending_gate
from orchestrator.adapters.outbound.records.yaml_record_parser import parse
from orchestrator.domain.model.record_status import RecordStatus
from orchestrator.domain.services.delivery_resolution import derive_from_records, gate_status
from capability_support import make_capabilities
from orchestrator.domain.model.run_config import RunConfig
_VENDORED_REACH = Path(__file__).resolve().parents[1] / 'devops' / 'vendor' / 'reach_gate.py'

class FakeStore:

    def __init__(self):
        self.configs = {}
        self.reopened = None
        self.scratch = {}

    def list_delivery_repos(self):
        return []

    def ensure(self, target):
        return target

    def register(self, workspace, request='', source=(), source_name=''):
        pass

    def write_gate(self, workspace, record, date, *, definition, expected_revision=''):
        pass

    def reopen_gate(self, workspace, record, *, expected_revision=''):
        self.reopened = (workspace, record)
        text = self.scratch.get(record)
        if text is not None:
            self.scratch[record] = GitHubRepoStore._reopened(record, text)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        self.configs[workspace] = dict(config)

class FakeSource:

    def __init__(self, store):
        self.store = store
        self.records = {}

    def scan(self):
        return []

    def state_of(self, repo):
        return replace(derive_from_records(repo, True, record_inputs(self.records.get(repo, {}))), scratch_ref='delivery/2026-08-18')

    def read_config(self, repo, *, revision=""):
        return self.store.configs.get(repo, {})

    def present_records(self, repo):
        return list(self.records.get(repo, {}).keys())

def _svc():
    store = FakeStore()
    source = FakeSource(store)
    return (make_capabilities(store, source=source), store, source)

@intent('INT-FC-R39')
def test_delivery_config_is_validated_persisted_and_governs_the_run():
    svc, store, source = _svc()
    dc = svc.delivery_config.execute('r')
    assert dc['mode'] == 'interactive'
    assert 'presence' not in dc
    svc.set_delivery_config.execute('r', 'one-shot', **command_kwargs('r'))
    assert store.configs['r'] == {'mode': 'one-shot'}
    with pytest.raises(ValueError):
        svc.set_delivery_config.execute('r', 'bogus', **command_kwargs('r'))
    store.configs['r'] = {'mode': 'one-shot', 'presence': 'unattended'}
    svc.set_delivery_config.execute('r', 'one-shot', **command_kwargs('r'))
    assert store.configs['r'] == {'mode': 'one-shot'}
    source.records['r'] = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: 2026-07-09\nreviewed: 2026-01-01\n---\n'}
    wf = svc.drive.execute('r', RunConfig('cred', 'r', True), 'run1', **command_kwargs('r')).workflow
    wf = json.loads(wf.executor_payload)
    # One-shot governed the run: it compiled no gate step and no suspend.
    names = [t['name'] for t in wf['spec']['templates']]
    assert not any((n.startswith('gate-') for n in names))
    assert not any(('suspend' in t for t in wf['spec']['templates']))
    worker_env = next((t for t in wf['spec']['templates'] if t['name'].startswith('worker-')))['container']['env']
    assert not any((e['name'] == 'FC_PRESENCE' for e in worker_env))
    assert 'foundry-console/presence' not in wf['metadata']['labels']

@intent('INT-FC-R178')
def test_a_mode_change_is_what_the_next_read_of_the_line_answers():
    """Reads serve the observed projection, which collection refreshes only when the
    repository is next due; a committed mode reaches it at once, and the command answers
    the mode it committed even while a re-read of the branch still lags the write."""
    svc, store, source = _svc()
    source.read_config = lambda repo, *, revision='': {}
    assert svc.delivery_config.execute('r')['mode'] == 'interactive'
    answer = svc.set_delivery_config.execute('r', 'one-shot', **command_kwargs('r'))
    assert store.configs['r'] == {'mode': 'one-shot'}
    assert answer['mode'] == 'one-shot'
    assert svc.delivery_config.execute('r')['mode'] == 'one-shot'
    svc.set_delivery_config.execute('r', 'interactive', **command_kwargs('r'))
    assert svc.delivery_config.execute('r')['mode'] == 'interactive'

@intent('INT-FC-R40')
def test_reopen_unsigns_the_gate_and_flags_downstream_for_review():
    assert gate_status(record_header(_pending_gate('---\nstatus: complete\ngate: design\nsigned: 2026-01-02\nreviewed: 2026-01-01\n---\n')), 'design') is None
    svc, store, source = _svc()
    source.records['r3'] = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n', 'design.md': '---\nstatus: complete\ngate: design\nsigned: 2026-01-02\nreviewed: 2026-01-01\n---\n', 'handoff.md': '---\nstatus: complete\ngate: plan\nsigned: 2026-01-03\nreviewed: 2026-01-01\n---\n', 'build.md': '---\nstatus: complete\ngate: delivery\nsigned: 2026-01-04\nreviewed: 2026-01-01\n---\n'}
    svc.reopen.execute('r3', 'scope', **command_kwargs('r3'))
    assert store.reopened == ('r3', 'proposal.md')
    dto = overview_dto(svc.delivery_overview.execute('r3'))
    by = {p['name']: p for p in dto['phases']}
    assert dto['phase'] == 'scope' and by['scope']['is_current']
    assert by['design']['record_present'] and by['design']['needs_review']
    assert by['build+ship']['record_present'] and by['build+ship']['needs_review']
    assert not by['scope']['needs_review']
_CLOSED_HANDOFF = "---\nphase: intent+plan\nskill: intent-session\nstatus: complete\ngate: plan\nsigned: 2026-08-24\nreviewed: 2026-08-24\nrun: r1\nattempt: 1\nmode: one-shot\nstarted: 2026-08-24T09:00:00Z\nfinished: 2026-08-24T17:00:00Z\ncredential_ref: fc-run-abc123\n---\n\n# Build handoff\n\nAttempt 1's plan.\n"

@intent('INT-FC-R40')
def test_reopen_demotes_the_record_and_clears_the_previous_attempts_review(monkeypatch):
    """A re-open hands the record back opened-for-work, so the phase the operator sent the
    line back to reads `status: in-progress` and carries no review.

    `reviewed:` is the field that makes this a safety property rather than tidiness: the
    stamper takes a dated `reviewed:` as sufficient evidence and signs without a verdict,
    so a date carried across a re-drive lets the ordinary stamp command close the new
    attempt's gate over the old attempt's review, with no refusal from any guard (#77,
    ai-assessment delivery/2026-08-11). This pins it at the port the cockpit calls."""
    monkeypatch.setattr(github_store, '_REACH_HELPER', str(_VENDORED_REACH))
    svc, store, source = _svc()
    store.scratch['handoff.md'] = _CLOSED_HANDOFF
    source.records['r4'] = {'proposal.md': 'proposal approved 2026-08-01', 'design.md': 'design approved 2026-08-10', 'handoff.md': _CLOSED_HANDOFF}
    svc.reopen.execute('r4', 'intent+plan', **command_kwargs('r4'))
    assert store.reopened == ('r4', 'handoff.md')
    front = parse(store.scratch['handoff.md'])
    assert front.status == RecordStatus.IN_PROGRESS
    assert front.reviewed is False
    assert front.signed is False
    assert front.run == 'r1' and front.attempt == 1
    assert "Attempt 1's plan." in store.scratch['handoff.md']

class FakeCreds:

    def __init__(self):
        self.store = {}

    def put_delivery(self, slug, credential):
        self.store[slug] = credential

    def has_delivery(self, slug):
        return slug in self.store

    def get_delivery(self, slug):
        return self.store.get(slug, '')

    def delivery_ref(self, slug):
        return f'fc-delivery-{slug}'

@intent('INT-FC-R51')
def test_target_selection_records_agent_and_model_console_local():
    from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
    store = FakeStore()
    source = FakeSource(store)
    creds = FakeCreds()
    svc = make_capabilities(store, source=source, credentials=creds, config=InMemoryConfigStore())
    svc.set_agent.execute('My Haiku', 'claude', '', 'haiku', 'oat-tok', **command_kwargs(''))
    svc.apply_agent_to_delivery.execute('example-org/acme', 'My Haiku', **command_kwargs('example-org/acme'))
    dc = svc.delivery_config.execute('example-org/acme')
    assert dc['agent'] == 'My Haiku' and dc['model'] == 'haiku' and (dc['credentialed'] is True)
    assert 'example-org/acme' not in store.configs
    svc.apply_agent_to_delivery.execute('example-org/acme', 'My Haiku', 'sonnet', **command_kwargs('example-org/acme'))
    dc2 = svc.delivery_config.execute('example-org/acme')
    assert dc2['agent'] == 'My Haiku' and dc2['model'] == 'sonnet'
    svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'opus', None, **command_kwargs('example-org/acme'))
    dc3 = svc.delivery_config.execute('example-org/acme')
    assert dc3['agent'] == '' and dc3['model'] == 'opus'

@intent('INT-FC-R45')
def test_per_target_selection_is_console_local_and_the_credential_backs_the_run():
    from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
    store = FakeStore()
    source = FakeSource(store)
    creds = FakeCreds()
    svc = make_capabilities(store, source=source, credentials=creds, config=InMemoryConfigStore())
    cfg = svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'haiku', 'oat-tok', **command_kwargs('example-org/acme'))
    assert cfg['credentialed'] is True and cfg['model'] == 'haiku'
    assert creds.store['acme'] == 'oat-tok'
    assert 'example-org/acme' not in store.configs
    assert 'oat-tok' not in str(store.configs)
    source.records['example-org/acme'] = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: 2026-07-09\nreviewed: 2026-01-01\n---\n'}
    wf = svc.drive.execute('example-org/acme', RunConfig(None, 'example-org/acme', True), 'run9', **command_kwargs('example-org/acme')).workflow
    wf = json.loads(wf.executor_payload)
    cred_env = [e for t in wf['spec']['templates'] if t['name'].startswith('worker-') for e in t['container']['env'] if e['name'] == 'FC_MODEL_CREDENTIAL'][0]
    assert cred_env['valueFrom']['secretKeyRef']['name'] == 'fc-delivery-acme'

@intent('INT-FC-R72')
def test_seating_a_credential_writes_no_repo_file():
    """Issue #4: seating a maintenance worker credential once wrote .delivery/config.json onto
    the target's main, fabricating a delivery scratch just to hold agent config. The selection
    is now Console-local, so a bare repo stays bare - only the per-slug Secret is seated."""
    from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
    store = FakeStore()
    source = FakeSource(store)
    creds = FakeCreds()
    svc = make_capabilities(store, source=source, credentials=creds, config=InMemoryConfigStore())
    svc.set_agent.execute('Sub', 'claude', '', 'haiku', 'tok', **command_kwargs(''))
    svc.apply_agent_to_delivery.execute('example-org/acme-library', 'Sub', **command_kwargs('example-org/acme-library'))
    assert store.configs == {}
    assert creds.store['acme-library'] == 'tok'
    assert svc.delivery_config.execute('example-org/acme-library')['credentialed'] is True
    svc.set_delivery_model.execute('example-org/other', 'claude', 'https://api.deepseek.com', 'deepseek-chat', 'sk', **command_kwargs('example-org/other'))
    assert store.configs == {}

@intent('INT-FC-R45')
def test_config_store_names_stay_rfc1123_for_camelcase_slugs():
    """A camelCase repo (SolveOS) keeps its slug case to match studio keys (R57), but the
    Kubernetes object stored under it MUST still be a valid name. kubectl rejects any uppercase,
    so an un-lowercased ConfigMap name (fc-target-SolveOS) made apply-agent return 422 and left
    the masthead picker looking like a silent no-op. The config store must lowercase the object
    name like the credential store already does, and both must agree on the target's object."""
    import re
    from orchestrator.adapters.outbound.settings.k8s_config_store import K8sConfigStore
    from orchestrator.adapters.outbound.credentials.k8s_credential_store import K8sCredentialStore
    from orchestrator.domain.delivery import delivery_slug
    rfc1123 = re.compile('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
    slug = delivery_slug('Example-Org-Of-Engineering/SolveOS')
    assert slug == 'SolveOS'
    cfg = K8sConfigStore()
    cm = cfg._cm(f'target-{slug}')
    sec = cfg._sec(f'target-{slug}')
    assert cm == 'fc-target-solveos' and rfc1123.match(cm)
    assert sec == 'fc-target-solveos-key' and rfc1123.match(sec)
    creds = K8sCredentialStore()
    assert creds.delivery_ref(slug) == 'fc-delivery-solveos'
    assert cfg._cm(f'target-{slug}') == cfg._cm('target-SolveOS')

@intent('INT-FC-R76')
def test_worker_timeout_is_per_delivery_defaults_to_an_hour_and_survives_a_model_change():
    from orchestrator.adapters.outbound.settings.in_memory_config_store import InMemoryConfigStore
    store = FakeStore()
    source = FakeSource(store)
    creds = FakeCreds()
    svc = make_capabilities(store, source=source, credentials=creds, config=InMemoryConfigStore())
    assert svc.delivery_config.execute('example-org/acme')['timeout_seconds'] == 3600
    assert config_dto(svc.delivery_config.execute('example-org/acme'))['timeout_hours'] == 1.0
    svc.set_delivery_timeout.execute('example-org/acme', 3 * 3600, **command_kwargs('example-org/acme'))
    assert svc.delivery_config.execute('example-org/acme')['timeout_seconds'] == 3 * 3600
    svc.set_agent.execute('Sub', 'claude', '', 'haiku', 'tok', **command_kwargs(''))
    svc.apply_agent_to_delivery.execute('example-org/acme', 'Sub', **command_kwargs('example-org/acme'))
    assert svc.delivery_config.execute('example-org/acme')['timeout_seconds'] == 3 * 3600
    svc.set_delivery_model.execute('example-org/acme', 'claude', '', 'opus', None, **command_kwargs('example-org/acme'))
    assert svc.delivery_config.execute('example-org/acme')['timeout_seconds'] == 3 * 3600
    source.records['example-org/acme'] = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: 2026-07-09\nreviewed: 2026-01-01\n---\n'}
    wf = svc.drive.execute('example-org/acme', RunConfig(None, 'example-org/acme', True), 'run1', **command_kwargs('example-org/acme')).workflow
    wf = json.loads(wf.executor_payload)
    workers = [t for t in wf['spec']['templates'] if t['name'].startswith('worker-')]
    assert workers and all((t['activeDeadlineSeconds'] == 3 * 3600 for t in workers))
    svc.set_delivery_timeout.execute('example-org/acme', 5, **command_kwargs('example-org/acme'))
    assert svc.delivery_config.execute('example-org/acme')['timeout_seconds'] == 600
