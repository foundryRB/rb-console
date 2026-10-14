"""INT-FC-R137: the console states its facts on the event bus one way. With the bus
unreachable, every act that would publish completes with the same outcome, the same
response, and the same derived state as it does with the bus up, each dropped publish
is logged, and every fact is one row of the console's own events page."""
from __future__ import annotations
from capability_support import with_lifecycle
from execution_fixtures import execution_graph, run_rows
from delivery_fixtures import record_inputs
from capability_support import invoke_helper
from capability_support import command_kwargs
import json
import logging
import re
from dataclasses import replace
from pathlib import Path
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.events.event_payload import SOURCE, cloud_event
from orchestrator.adapters.outbound.events.logging_event_publisher import LoggingEventPublisher
from orchestrator.application import events as vocabulary
from orchestrator.application.events import ACT_LAUNCHED, ACT_PARKED, GATE_REACHED, GATE_SIGNED, LINE_CLOSED, LINE_DELIVERED, LINE_LEARNED, LINE_STARTED, PHASE_ENTERED, PHASE_REOPENED, PHASE_STARTED, PR_JUDGED, PR_MERGED, RUN_COMPLETED, RUN_DEGRADED, TICKET_CLOSED, position_facts, state_fact
from orchestrator.domain.services.delivery_resolution import derive_from_records
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from capability_support import make_capabilities
from orchestrator.domain.delivery import AWAITING_GATE, DEGRADED, DELIVERED, LEARNED, RUN_PHASE
from orchestrator.domain.maintenance import VERDICT_PASS
from orchestrator.domain.model.run_config import RunConfig
from tests.test_maintenance_service import FakeActs, FakeConfig, FakeCredentials, FakeMSource, FakeWorkflows, _pr, _rev
from tests.test_maintenance_service import FakeRepos as MaintenanceRepos

class RecordingPublisher:
    """A bus that is up. It builds the real envelope before recording, so a payload the
    adapter could not serialize fails here instead of being dropped in production."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str, dict]] = []

    def publish(self, *, event_type, subject, data) -> None:
        cloud_event(event_type=event_type, subject=subject, data=data)
        self.published.append((event_type, subject, data))

    @property
    def types(self) -> list[str]:
        return [t for t, _s, _d in self.published]

class RaisingPublisher:
    """A bus that is down in the least forgiving way: every publish explodes."""

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def publish(self, *, event_type, subject, data) -> None:
        self.attempts.append(event_type)
        raise ConnectionError('bus unreachable')

class Repos:
    """A repo store whose records live in memory, so sign and re-open are observable."""

    def __init__(self, tmp: Path, contents: dict[str, str] | None=None):
        self.tmp = tmp
        self.contents = dict(contents or {})
        self.registered: list[str] = []
        self.closed: list[str] = []

    def list_delivery_repos(self):
        return [str(self.tmp)]

    def ensure(self, target):
        p = self.tmp / target
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    def register(self, workspace, request='', source=(), source_name=''):
        scratch = Path(workspace) / '.delivery'
        scratch.mkdir(parents=True, exist_ok=True)
        (scratch / 'README.md').write_text('scratch', encoding='utf-8')
        self.registered.append(workspace)

    def write_gate(self, repo, record, date, *, definition, expected_revision=''):
        self.contents[record] = f'---\nstatus: complete\ngate: proposal\nsigned: {date}\nreviewed: 2026-01-01\n---\n'

    def reopen_gate(self, repo, record, *, expected_revision=''):
        self.contents[record] = '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n'

    def append_journal(self, workspace, entry):
        pass

    def close_line(self, workspace, *, expected_revision=''):
        import shutil
        self.closed.append(workspace)
        shutil.rmtree(Path(workspace) / '.delivery', ignore_errors=True)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

class RecordSource:
    """state_of over the in-memory records (the remote source's shape)."""

    def __init__(self, repos: Repos):
        self._repos = repos

    def list_org_repos(self):
        return []

    def state_of(self, repo):
        return derive_from_records(repo, True, record_inputs(dict(self._repos.contents)))

    def scan(self):
        return [self.state_of('acme')]

    def read_config(self, repo, *, revision=""):
        return {}

    def present_records(self, repo):
        return []

class ScratchSource:
    """state_of over a real scratch on disk with the line's ref attached, so drive
    compiles exactly as in production."""

    def state_of(self, repo):
        return replace(derive_state(repo), scratch_ref='delivery/2026-08-22')

    def scan(self):
        return []

    def read_config(self, repo, *, revision=""):
        return {}

    def present_records(self, repo):
        return []

class Workflows:

    def __init__(self, rows=None):
        self.rows = rows or []
        self.submitted: list[dict] = []

    def submit(self, wf):
        self.submitted.append(wf)
        return f'handle-{len(self.submitted)}'

    def list_runs(self):
        return run_rows(self.rows)

    def status(self, handle):
        return 'Succeeded'

    def graph(self, handle):
        return execution_graph({'nodes': []})
CFG = RunConfig('tok', 'acme', True)
PENDING = {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n'}

def _scratch(tmp_path: Path) -> str:
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    return str(tmp_path / 'acme')

def _start(tmp_path, events):
    svc = make_capabilities(Repos(tmp_path), events=events)
    return (svc, lambda: svc.start.execute('acme', CFG, **command_kwargs('acme')).kind)

def _drive(tmp_path, events):
    repo = _scratch(tmp_path)
    svc = make_capabilities(Repos(tmp_path), workflows=Workflows(), source=ScratchSource(), events=events)
    return (svc, lambda: svc.drive.execute(repo, CFG, 'r-1', **command_kwargs(repo)).state.phase)

def _sign(tmp_path, events):
    repos = Repos(tmp_path, PENDING)
    svc = make_capabilities(repos, source=RecordSource(repos), events=events)
    return (svc, lambda: svc.sign_gate.execute('acme', **command_kwargs('acme')).gates[0].signed)

def _reopen(tmp_path, events):
    repos = Repos(tmp_path, {'proposal.md': '---\nstatus: complete\ngate: proposal\nsigned: 2026-08-01\nreviewed: 2026-01-01\n---\n'})
    svc = make_capabilities(repos, source=RecordSource(repos), events=events)
    return (svc, lambda: svc.reopen.execute('acme', 'scope', **command_kwargs('acme')).status)

def _close(tmp_path, events):
    repo = _scratch(tmp_path)
    svc = make_capabilities(Repos(tmp_path), events=events)
    return (svc, lambda: svc.close_line.execute(repo, **command_kwargs(repo)).exists)

def _maintenance(events, msource=None, acts=None, workflows=None):
    return make_capabilities(MaintenanceRepos(), workflows=workflows or FakeWorkflows('Succeeded'), credentials=FakeCredentials(), config=FakeConfig('fc-git'), msource=msource or FakeMSource(), macts=acts or FakeActs(), events=events)

def _mdrive(tmp_path, events):
    svc = _maintenance(events)
    return (svc, lambda: svc.maintenance_drive.execute('org/app', 'resolve', 7, 'gated', RunConfig('tok', 'org/app', True), **command_kwargs('org/app')).act)

def _mmerge(tmp_path, events):
    green = [{'status': 'completed', 'conclusion': 'success'}]
    svc = _maintenance(events, msource=FakeMSource(prs=[_pr(12)], reviews={12: [_rev('VERDICT: PASS')]}, checks={'a' * 40: green}))
    return (svc, lambda: svc.maintenance_merge.execute('org/app', 12, **command_kwargs('org/app')))

def _mclose(tmp_path, events):
    svc = _maintenance(events)
    return (svc, lambda: svc.maintenance_close_ticket.execute('org/app', 7, **command_kwargs('org/app')))
_ACTS = [pytest.param(_start, [LINE_STARTED], id='start'), pytest.param(_drive, [PHASE_STARTED], id='drive'), pytest.param(_sign, [GATE_SIGNED], id='sign'), pytest.param(_reopen, [PHASE_REOPENED], id='reopen'), pytest.param(_close, [LINE_CLOSED], id='close'), pytest.param(_mdrive, [ACT_LAUNCHED], id='maintenance-drive'), pytest.param(_mmerge, [PR_MERGED], id='maintenance-merge'), pytest.param(_mclose, [TICKET_CLOSED], id='maintenance-close')]

@intent('INT-FC-R137')
@pytest.mark.parametrize(('factory', 'facts'), _ACTS)
def test_every_act_is_identical_with_the_bus_down(tmp_path, caplog, factory, facts):
    up = RecordingPublisher()
    _svc, act = factory(tmp_path / 'up', up)
    result_up = act()
    assert up.types == facts
    for _t, subject, data in up.published:
        assert subject
        assert json.dumps(data)
    down = RaisingPublisher()
    _svc, act = factory(tmp_path / 'down', down)
    with caplog.at_level(logging.WARNING, logger='orchestrator'):
        result_down = act()
    assert down.attempts == facts, 'the act must still attempt each publish'
    assert result_down == result_up
    for fact in facts:
        assert any((fact in r.getMessage() for r in caplog.records)), f'a dropped {fact} must be logged'

@intent('INT-FC-R137')
def test_the_judge_states_its_verdict_and_its_act():
    green = [{'status': 'completed', 'conclusion': 'success'}]
    passing = {12: [_rev('ok\nVERDICT: PASS')]}
    up = RecordingPublisher()
    svc = _maintenance(up, FakeMSource(prs=[_pr(12, head='fix/7-x')], reviews=passing, checks={'a' * 40: green}), FakeActs())
    svc.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc, '_judge_oneshot_runs')
    assert up.types == [ACT_LAUNCHED, PR_JUDGED, PR_MERGED]
    judged = up.published[1][2]
    assert judged['verdict'] == VERDICT_PASS and judged['gate'] == 'merge' and (judged['pr'] == 12)
    assert up.published[2][2]['by'] == 'judge'
    up2 = RecordingPublisher()
    svc2 = _maintenance(up2, FakeMSource(prs=[_pr(12)], reviews={}, checks={'a' * 40: green}), FakeActs())
    svc2.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc2, '_judge_oneshot_runs')
    assert up2.types == [ACT_LAUNCHED, PR_JUDGED, ACT_PARKED]
    assert 'parked' in up2.published[2][2]['reason']
    acts = FakeActs()
    down = RaisingPublisher()
    svc3 = _maintenance(down, FakeMSource(prs=[_pr(12, head='fix/7-x')], reviews=passing, checks={'a' * 40: green}), acts)
    svc3.maintenance_drive.execute('org/app', 'resolve', 7, 'one-shot', RunConfig('tok', 'org/app', True), **command_kwargs('org/app'))
    invoke_helper(svc3, '_judge_oneshot_runs')
    assert acts.merged == [('org/app', 12)]
    assert down.attempts == [ACT_LAUNCHED, PR_JUDGED, PR_MERGED]

@intent('INT-FC-R137')
def test_position_moves_are_stated_by_their_destination():
    """One type per destination status, so a consumer subscribes to the fact it reacts to."""
    scope = derive_from_records('acme', True, record_inputs({}))
    assert scope.status == RUN_PHASE
    gated = derive_from_records('acme', True, record_inputs(PENDING))
    assert gated.status == AWAITING_GATE
    assert position_facts(None, gated) == []
    assert position_facts(gated, gated) == []
    assert [t for t, _ in position_facts(scope, gated)] == [GATE_REACHED]
    assert position_facts(scope, gated)[0][1]['gate'] == 'proposal'
    assert [t for t, _ in position_facts(gated, scope)] == [PHASE_ENTERED]
    degraded = replace(scope, status=DEGRADED)
    assert [t for t, _ in position_facts(scope, degraded)] == [RUN_DEGRADED]
    delivered = replace(scope, status=DELIVERED, phase=None)
    assert [t for t, _ in position_facts(scope, delivered)] == [LINE_DELIVERED]
    learned = replace(delivered, status=LEARNED, learned_on='2026-08-22')
    facts = position_facts(delivered, learned)
    assert [t for t, _ in facts] == [LINE_LEARNED] and facts[0][1]['learned_on'] == '2026-08-22'

@intent('INT-FC-R137')
def test_the_tick_narrates_what_moved_and_primes_silently_on_a_cold_start(tmp_path):
    from orchestrator.adapters.outbound.memory.index import DeliveryIndex
    repos = Repos(tmp_path)
    source = RecordSource(repos)
    rows = [{'name': 'delivery-acme-1', 'handle': 'live:x/1', 'phase': 'Running', 'repo_slug': 'acme'}]
    wf = Workflows(rows)
    up = RecordingPublisher()
    svc = make_capabilities(repos, workflows=wf, index=DeliveryIndex(), source=source, events=up)
    svc.refresh.execute()
    assert up.types == []
    repos.contents.update(PENDING)
    rows[0]['phase'] = 'Succeeded'
    svc.refresh.execute()
    assert sorted(up.types) == sorted([GATE_REACHED, RUN_COMPLETED])
    run = next((d for t, _s, d in up.published if t == RUN_COMPLETED))
    assert run['run'] == 'delivery-acme-1' and run['phase'] == 'Succeeded' and (run['stop'] == '')
    svc.refresh.execute()
    assert len(up.published) == 2
    down = RaisingPublisher()
    svc_down = make_capabilities(repos, workflows=wf, index=DeliveryIndex(), source=source, events=down)
    svc_down.refresh.execute()
    repos.contents['proposal.md'] = '---\nstatus: complete\ngate: proposal\nsigned: 2026-08-22\nreviewed: 2026-01-01\n---\n'
    svc_down.refresh.execute()
    assert down.attempts == [PHASE_ENTERED]
    assert svc_down.status.execute('acme').status == RUN_PHASE

@intent('INT-FC-R137')
def test_state_fact_never_raises_and_a_console_without_a_bus_states_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger='orchestrator'):
        state_fact(RaisingPublisher(), event_type=LINE_STARTED, subject='acme', data={})
    assert any((LINE_STARTED in r.getMessage() for r in caplog.records))
    state_fact(None, event_type=LINE_STARTED, subject='acme', data={})

@intent('INT-FC-R137')
def test_the_envelope_is_a_cloudevent_carrying_pointers_not_payloads():
    event = json.loads(cloud_event(event_type=LINE_STARTED, subject='acme', data={'repo': 'acme'}))
    assert event['specversion'] == '1.0'
    assert event['type'] == LINE_STARTED
    assert event['subject'] == 'acme'
    assert event['source'] == SOURCE
    assert event['datacontenttype'] == 'application/json'
    assert event['id'] and event['time']
    other = json.loads(cloud_event(event_type=LINE_STARTED, subject='acme', data={}))
    assert other['id'] != event['id']
    with pytest.raises(TypeError):
        cloud_event(event_type=LINE_STARTED, subject='acme', data={'state': object()})
    LoggingEventPublisher().publish(event_type=LINE_STARTED, subject='acme', data={'state': object()})
_EVENTS_PAGE = Path(__file__).resolve().parents[1] / 'docs/src/content/docs/reference/events.md'

@intent('INT-FC-R137')
def test_the_events_page_states_exactly_the_types_the_console_emits():
    """REF-Events section 3: each owner states its own types on its own page, held
    against the publisher by its own tests. Neither the page nor the constants move alone."""
    emitted = {value for name, value in vars(vocabulary).items() if name.isupper() and isinstance(value, str) and value.startswith('com.foundry.')}
    assert emitted
    domains = {value.split('.')[2] for value in emitted}
    assert domains == {'delivery', 'maintenance'}, 'every type is under a domain this console owns'
    stated = set(re.findall('^\\| `(com\\.foundry\\.[a-z.]+)` \\|', _EVENTS_PAGE.read_text(encoding='utf-8'), flags=re.M))
    assert stated == emitted, f'page states {sorted(stated - emitted)} the console never emits; console emits {sorted(emitted - stated)} the page never states'
