"""The worker runner builds the spawn invocation deterministically and stays
guarded (no live spawn without FC_DRIVE_LIVE and a credential), and the service's advance
executes a planned launch through it."""
from capability_support import with_lifecycle
from capability_support import command_kwargs
import os
import shutil
import subprocess
from pathlib import Path
import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.agents.claude_worker_runner import ClaudeWorkerRunner, build_invocation
from capability_support import make_capabilities
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.worker_launch import WorkerLaunch

def posix_bash() -> str | None:
    """An absolute path to a bash that can actually run a POSIX script, or None.

    Two Windows traps make a bare ``subprocess.run(["bash", ...])`` unreliable, and both are
    why this resolves an absolute path instead. CreateProcess searches the system directory
    BEFORE PATH, so plain "bash" finds System32's WSL launcher rather than the Git bash that
    is first on PATH; and that launcher exits non-zero when no distro is installed. So each
    candidate is probed for a working shell rather than trusted for existing.
    """
    candidates = [shutil.which('bash')]
    if os.name == 'nt':
        candidates += ['C:\\Program Files\\Git\\bin\\bash.exe', 'C:\\Program Files (x86)\\Git\\bin\\bash.exe']
    for cand in candidates:
        if not cand or not Path(cand).exists():
            continue
        try:
            probe = subprocess.run([cand, '-c', 'printf ok'], capture_output=True, text=True, timeout=30)
        except OSError:
            continue
        if probe.returncode == 0 and probe.stdout.strip() == 'ok':
            return cand
    return None
PLAN = WorkerLaunch(repo='/w/x', phase='scope', skill='deliver-engagement', credential_ref='tok', mcp_endpoints=('playbook-studio', 'estimatekit'), prompt='Run the deliver-engagement skill for /w/x. Do not sign any gate.')

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
        (Path(workspace) / '.delivery').mkdir(parents=True, exist_ok=True)

    def write_config(self, workspace, config, *, lifecycle=None):
        config = with_lifecycle(config, lifecycle)
        import json
        from pathlib import Path
        scratch = Path(str(workspace)) / '.delivery'
        if scratch.is_dir():
            (scratch / 'config.json').write_text(json.dumps(config), encoding='utf-8')

@intent('INT-FC-R15')
def test_worker_runner_builds_invocation_and_stays_guarded(monkeypatch):
    argv = build_invocation(PLAN)
    assert argv[0] == 'claude'
    assert '-p' in argv
    assert PLAN.prompt in argv
    monkeypatch.delenv('FC_DRIVE_LIVE', raising=False)
    handle = ClaudeWorkerRunner().launch(PLAN)
    assert handle.startswith('dry-run:')

@intent('INT-FC-R16')
def test_advance_executes_a_planned_launch_through_the_runner(tmp_path, monkeypatch):
    monkeypatch.delenv('FC_DRIVE_LIVE', raising=False)
    service = make_capabilities(FakeRepos(tmp_path), ClaudeWorkerRunner())
    cfg = RunConfig(worker_credential='tok', repo_target='acme', repo_rights=True)
    started = service.start.execute('acme', cfg, **command_kwargs('acme'))
    advanced = service.advance.execute(started.state.repo, cfg, **command_kwargs(started.state.repo))
    assert advanced.kind == 'launch'
    assert advanced.handle is not None
    assert advanced.handle.startswith('dry-run:')

@intent('INT-FC-R50')
def test_worker_self_validation_matches_the_domain_contract():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert '[ -f "$rec" ]' in entrypoint
    assert '[ -s "$rec" ]' in entrypoint
    assert "grep -qiE '^status:[[:space:]]*complete'" not in entrypoint
    assert '[ -n "${FC_RECORD}" ]' in entrypoint
    assert 'deliberate park); degraded stop, not retrying' in entrypoint

@intent('INT-FC-R50')
def test_the_scratch_mounts_as_a_worktree_and_every_scratch_commit_names_the_ref():
    import re
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert 'git fetch origin "refs/heads/${FC_SCRATCH_REF}:refs/heads/${FC_SCRATCH_REF}"' in entrypoint
    assert 'git worktree add .delivery "$FC_SCRATCH_REF"' in entrypoint
    assert 'FC_RECORD is set but FC_SCRATCH_REF is empty' in entrypoint
    assert entrypoint.count('git -C .delivery push origin "HEAD:refs/heads/${FC_SCRATCH_REF}"') == 5
    code = '\n'.join((line for line in entrypoint.splitlines() if not line.lstrip().startswith('#')))
    assert 'git add .delivery' not in code
    assert not re.search('^\\s*git push\\s*$', code, re.MULTILINE)

@intent('INT-FC-R89')
def test_checkout_identity_uses_the_token_user_and_keeps_the_display_name_for_commits():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    helper = entrypoint.split("<<'OWN_HELPER'", 1)[1].split('\nOWN_HELPER', 1)[0]
    assert 'username=x-access-token' in helper
    assert 'git clone "https://github.com/${repo_path}.git"' in entrypoint
    assert 'https://${GIT_USER}:' not in entrypoint
    assert "tr -d '[:space:]'" in entrypoint
    assert 'git config --global user.name "$GIT_USER"' in entrypoint

@intent('INT-FC-R52')
def test_gates_close_through_the_playbook_stamper_after_a_passing_review():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert '[ "${FC_MODE:-}" = "one-shot" ]' in entrypoint
    assert '[ "${record_status:-}" = "gate" ]' in entrypoint
    assert 'sort -V | tail -n1' in entrypoint
    assert 'review_prompt' not in entrypoint
    assert 'no fresh-eyes review for' in entrypoint
    assert 'VERDICT:PASS' in entrypoint.replace('"', '')
    assert 'python3 "$FC_STAMP_HELPER"' in entrypoint
    assert '--review-verdict pass' in entrypoint
    assert '--review-only' in entrypoint
    assert 'sed -i' not in entrypoint
    assert 'fresh-eyes review did not pass' in entrypoint
    from orchestrator.domain.services.delivery_launch import build_worker_launch
    from orchestrator.domain.model.run_mode import RunMode
    one = build_worker_launch('acme', 'design', 'design-session', RunConfig('t', 'acme', True, RunMode.ONE_SHOT))
    assert 'frontmatter `signed:` line' in one.prompt and 'Never hold for a human' in one.prompt
    inter = build_worker_launch('acme', 'design', 'design-session', RunConfig('t', 'acme', True, RunMode.INTERACTIVE))
    assert 'Never hold for a human' not in inter.prompt
    from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
    from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
    from orchestrator.domain.model.run_mode import RunMode
    import tempfile
    import pathlib
    with tempfile.TemporaryDirectory() as td:
        scratch = pathlib.Path(td) / 'acme' / '.delivery'
        scratch.mkdir(parents=True)
        (scratch / 'README.md').write_text('scratch', encoding='utf-8')
        from dataclasses import replace
        state = replace(derive_state(str(pathlib.Path(td) / 'acme')), scratch_ref='delivery/2026-08-18')
        wf = compile_workflow('acme', state, RunConfig('tok', 'acme', True, RunMode.ONE_SHOT), run_id='r1')
    scope = next((t for t in wf['spec']['templates'] if t['name'] == 'worker-scope'))
    env = {e['name']: e.get('value') for e in scope['container']['env']}
    assert env['FC_GATE'] == 'proposal'

@intent('INT-FC-R102')
def test_verdict_parse_survives_markdown_and_trailing_prose(tmp_path):
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert "awk 'NF{last=$0} END{print last}'" not in entrypoint
    assert "grep -oiE 'VERDICT:[[:space:]]*(PASS|FAIL)'" in entrypoint
    bash = posix_bash()
    if bash is None:
        pytest.skip('no working POSIX bash on this host')
    script = tmp_path / 'parse.sh'
    script.write_text('verdict=$(grep -oiE \'VERDICT:[[:space:]]*(PASS|FAIL)\' "$1" | tail -n1 || true)\nprintf \'%s\' "$(printf \'%s\' "$verdict" | tr -d \'[:space:]\' | tr \'[:lower:]\' \'[:upper:]\')"\n', encoding='utf-8', newline='')
    passing = 'The design.md frontmatter declares `signed: pending`. This is the correct state.\n\n---\n\n**VERDICT: PASS**\n\nThe design phase record answers its question with concrete artifacts.'
    review = tmp_path / 'pass.md'
    review.write_text(passing, encoding='utf-8')
    out = subprocess.run([bash, str(script), review.as_posix()], capture_output=True, text=True, check=True)
    assert out.stdout == 'VERDICT:PASS'
    failing = 'Findings: a traceability gap.\n\n**VERDICT: FAIL**\n\nFix the gap before resubmitting.'
    review = tmp_path / 'fail.md'
    review.write_text(failing, encoding='utf-8')
    out = subprocess.run([bash, str(script), review.as_posix()], capture_output=True, text=True, check=True)
    assert out.stdout == 'VERDICT:FAIL'

@intent('INT-FC-R103')
def test_a_self_signed_record_is_stripped_to_pending_and_still_reviewed(tmp_path):
    import re
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert 'arrived self-signed by the agent' in entrypoint
    assert 'strip agent-signed gate to pending' in entrypoint
    assert entrypoint.index('arrived self-signed') < entrypoint.index('sort -V | tail -n1')
    heredoc = re.search('python3 - \\"\\$rec\\" <<\'PY\'\\n(.*?)\\nPY\\n', entrypoint, re.DOTALL)
    assert heredoc, 'the strip heredoc must exist in the entrypoint'
    strip_py = tmp_path / 'strip.py'
    strip_py.write_text(heredoc.group(1), encoding='utf-8')
    record = tmp_path / 'handoff.md'
    record.write_text('---\nphase: plan\nstatus: complete\ngate: plan\nsigned: 2026-07-20\nreviewed: 2026-07-20\n---\n\nPlan gate awaits engine stamp. Started 2026-07-20.\n', encoding='utf-8')
    subprocess.run([sys.executable, str(strip_py), str(record)], check=True)
    out = record.read_text(encoding='utf-8')
    assert 'signed: pending' in out
    assert 'reviewed: 2026-07-20' not in out
    assert 'Plan gate awaits engine stamp. Started 2026-07-20.\n' in out

@intent('INT-FC-R104')
def test_the_review_artifact_is_committed_and_passed_as_review_log():
    root = Path(__file__).resolve().parents[1]
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    lookup = 'find .delivery/reviews -maxdepth 1 -name "${FC_RECORD%.md}-*.md"'
    assert lookup in entrypoint and 'sort -V | tail -n1' in entrypoint
    assert 'review_out' not in entrypoint and 'review_prompt' not in entrypoint
    # Managed review-only, one-shot stamp, the review-only a refused one-shot stamp records
    # before its terminal stop (#181), and interactive review-only.
    assert entrypoint.count('--review-verdict pass') == 4
    assert entrypoint.count('--review-log "$review_log"') == entrypoint.count('--review-verdict pass')
    assert entrypoint.index(lookup) < entrypoint.index('python3 "$FC_STAMP_HELPER"')
    assert entrypoint.index('python3 "$FC_STAMP_HELPER"') < entrypoint.rindex('git -C .delivery add')

@intent('INT-FC-R111')
def test_both_record_helpers_reach_the_pod_and_the_frontmatter_is_helper_written(tmp_path):
    import re
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    for helper in ('establish_scratch.py', 'reach_gate.py', 'stamp_gate.py'):
        assert (root / 'devops' / 'vendor' / helper).is_file()
    refresh = (root / 'devops' / 'vendor' / 'update-vendored-helpers.sh').read_text(encoding='utf-8')
    delivery = [ln for ln in refresh.splitlines() if 'skills/deliver-engagement|' in ln]
    assert len(delivery) == 1, 'the delivery helpers must ride one source entry, not several'
    for helper in ('establish_scratch.py', 'reach_gate.py', 'stamp_gate.py'):
        assert helper in delivery[0]
    worker_df = (root / 'devops' / 'worker.Dockerfile').read_text(encoding='utf-8')
    assert 'COPY devops/vendor/establish_scratch.py /opt/foundry/establish_scratch.py' in worker_df
    assert 'COPY devops/vendor/reach_gate.py /opt/foundry/reach_gate.py' in worker_df
    assert 'COPY devops/vendor/stamp_gate.py /opt/foundry/stamp_gate.py' in worker_df
    console_df = (root / 'devops' / 'Dockerfile').read_text(encoding='utf-8')
    assert 'COPY devops/vendor/establish_scratch.py /opt/foundry/establish_scratch.py' in console_df
    assert 'COPY devops/vendor/reach_gate.py /opt/foundry/reach_gate.py' in console_df
    assert 'COPY devops/vendor/stamp_gate.py /opt/foundry/stamp_gate.py' in console_df
    entrypoint = (root / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert 'export FC_ESTABLISH_HELPER="${FC_ESTABLISH_HELPER:-/opt/foundry/establish_scratch.py}"' in entrypoint
    assert 'export FC_REACH_HELPER="${FC_REACH_HELPER:-/opt/foundry/reach_gate.py}"' in entrypoint
    assert 'export FC_STAMP_HELPER="${FC_STAMP_HELPER:-/opt/foundry/stamp_gate.py}"' in entrypoint
    from orchestrator.domain.services.delivery_launch import build_worker_launch
    from orchestrator.domain.model.run_mode import RunMode
    launch = build_worker_launch('acme', 'intent+plan', 'intent-session', RunConfig('t', 'acme', True, RunMode.ONE_SHOT))
    assert '$FC_REACH_HELPER' in launch.prompt and '$FC_STAMP_HELPER' in launch.prompt
    assert "never hand-write a record's frontmatter" in launch.prompt
    assert '--run "$FC_RUN" --mode "$FC_MODE" --credential-ref "$FC_CREDENTIAL_REF"' in launch.prompt
    from orchestrator.adapters.outbound.argo.delivery_workflow import compile_workflow
    import inspect
    from orchestrator.adapters.outbound.argo import worker_template as _wf
    src = inspect.getsource(_wf)
    assert '{"name": "FC_RUN", "value": run_id}' in src
    assert '{"name": "FC_CREDENTIAL_REF", "value": credential_secret}' in src
    assert 'python3 "$FC_REACH_HELPER"' not in entrypoint
    (tmp_path / '.delivery').mkdir()
    record = tmp_path / '.delivery' / 'handoff.md'
    record.write_text('---\ngate: plan\nstatus: gate\nphase: intent-plan\nsigned: pending\nonboarding_pr: https://github.com/acme/platform/pull/7\n---\n\n# Build handoff\n\nThe plan. Authored 2026-07-20.\n', encoding='utf-8')
    subprocess.run([sys.executable, str(root / 'devops' / 'vendor' / 'reach_gate.py'), '--repo', str(tmp_path), '--record', 'handoff.md', '--phase', 'intent+plan', '--skill', 'intent-session', '--gate', 'plan', '--status', 'gate', '--mode', 'one-shot', '--run', 'fc-run-abc123', '--credential-ref', 'fc-run-abc123'], check=True, capture_output=True)
    out = record.read_text(encoding='utf-8')
    front = out.split('---')[1]
    assert re.search('^phase: intent\\+plan$', front, re.M)
    assert re.search('^skill: intent-session$', front, re.M)
    assert re.search('^status: gate$', front, re.M)
    assert re.search('^signed: pending$', front, re.M)
    assert re.search('^run: fc-run-abc123$', front, re.M)
    assert re.search('^mode: one-shot$', front, re.M)
    assert re.search('^credential_ref: fc-run-abc123$', front, re.M)
    assert 'onboarding_pr: https://github.com/acme/platform/pull/7' in front
    assert '# Build handoff\n\nThe plan. Authored 2026-07-20.\n' in out

@intent('INT-FC-R152')
def test_the_mcp_config_lives_outside_the_clone():
    """The MCP config the worker writes carries the studios' Authorization headers, so it
    never sits at the clone root: there it is one broad `git add` away from the default
    branch, and `.mcp.json` at a repo root is the CLI's committable project config
    (playbook#189). It lives beside the clone under WORK_DIR and reaches the agent by
    explicit path."""
    entrypoint = (Path(__file__).resolve().parents[1] / 'devops' / 'worker-entrypoint.sh').read_text(encoding='utf-8')
    assert '> "${WORK_DIR}/mcp.json"' in entrypoint, 'the config is written beside the clone'
    assert '--mcp-config "${WORK_DIR}/mcp.json"' in entrypoint, 'and handed to the agent by that path'
    assert 'rm -f "${WORK_DIR}/mcp.json"' in entrypoint, 'and removed from there at the end'
    assert '> .mcp.json' not in entrypoint, 'nothing writes a config into the clone root'


def test_worker_image_bakes_the_same_immutable_playbook_as_its_helpers():
    import tarfile
    root = Path(__file__).resolve().parents[1]
    vendor = root / "devops" / "vendor"
    bundle = vendor / "playbook.tar.gz"
    with tarfile.open(bundle) as archive:
        names = archive.getnames()
        assert "REVISION" in names
        assert "AI-PLAYBOOK.md" in names
        assert any(name.endswith("skills/deliver-engagement/SKILL.md") for name in names)
    dockerfile = (root / "devops" / "worker.Dockerfile").read_text()
    assert "COPY devops/vendor/playbook.tar.gz /opt/foundry/playbook.tar.gz" in dockerfile
    assert "COPY devops/vendor/lifecycle.json /opt/foundry/lifecycle.json" in dockerfile
