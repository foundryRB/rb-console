"""Tests for the orchestrator service over a fake RepoStore: config refusal, the
start (register then plan scope) path, and suspending at a pending gate."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
from pathlib import Path
import pytest
from pytest_intent import intent
from capability_support import make_capabilities
from orchestrator.domain.model.run_config import RunConfig

class FakeRepos:

    def __init__(self, tmp):
        self.tmp = Path(tmp)
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
GOOD = RunConfig(worker_credential='tok', repo_target='acme', repo_rights=True)

@intent('INT-FC-R10')
def test_start_refuses_incomplete_config(tmp_path):
    service = make_capabilities(FakeRepos(tmp_path))
    with pytest.raises(ValueError):
        service.start.execute('acme', RunConfig(worker_credential=None, repo_target=None), **command_kwargs('acme'))

@intent('INT-FC-R11')
def test_start_registers_then_plans_scope(tmp_path):
    repos = FakeRepos(tmp_path)
    action = make_capabilities(repos).start.execute('acme', GOOD, **command_kwargs('acme'))
    assert repos.registered
    assert action.kind == 'launch'
    assert action.launch is not None
    assert action.launch.skill == 'deliver-engagement'

@intent('INT-FC-R12')
def test_plan_next_awaits_a_pending_gate(tmp_path):
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'proposal.md').write_text('---\nstatus: complete\ngate: proposal\nsigned: pending\nreviewed: 2026-01-01\n---\n', encoding='utf-8')
    action = make_capabilities(FakeRepos(tmp_path)).plan_next.execute(str(tmp_path / 'acme'), GOOD)
    assert action.kind == 'await-gate'
    assert action.gate == 'proposal'

@intent('INT-FC-R79')
def test_close_line_closes_the_line_through_the_store(tmp_path):
    scratch = tmp_path / 'acme' / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'proposal.md').write_text('done', encoding='utf-8')
    (scratch / 'journal.md').write_text('lessons', encoding='utf-8')
    repos = FakeRepos(tmp_path)
    state = make_capabilities(repos).close_line.execute((_command_repository := str(tmp_path / 'acme')), **command_kwargs(_command_repository))
    assert repos.closed == [str(tmp_path / 'acme')]
    assert not scratch.exists()
    assert state.exists is False and state.status == 'not-a-delivery'

@intent('INT-FC-R79')
def test_close_line_refuses_a_non_delivery(tmp_path):
    (tmp_path / 'bare').mkdir()
    repos = FakeRepos(tmp_path)
    with pytest.raises(ValueError):
        make_capabilities(repos).close_line.execute((_command_repository := str(tmp_path / 'bare')), **command_kwargs(_command_repository))
    assert repos.closed == []


@intent('INT-FC-R172')
def test_establishing_a_line_opened_without_the_console_pins_it_and_keeps_its_mode(tmp_path):
    import json
    from orchestrator.adapters.outbound.records.lifecycle_codec import decode_pin
    from orchestrator.domain.current_lifecycle import CURRENT_PLAYBOOK_REF
    line = tmp_path / 'acme'
    scratch = line / '.delivery'
    scratch.mkdir(parents=True)
    (scratch / 'README.md').write_text('scratch', encoding='utf-8')
    (scratch / 'config.json').write_text(json.dumps({'mode': 'one-shot'}), encoding='utf-8')
    service = make_capabilities(FakeRepos(tmp_path))
    service.establish.execute(str(line), **command_kwargs(str(line)))
    config = json.loads((scratch / 'config.json').read_text(encoding='utf-8'))
    assert config['mode'] == 'one-shot'
    pinned = decode_pin(config['lifecycle'])
    assert (pinned.source_ref, pinned.worker_image) == (CURRENT_PLAYBOOK_REF, 'worker:1.0.0')
