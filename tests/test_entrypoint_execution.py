"""Run devops/worker-entrypoint.sh for real: exit codes plus durable side effects.

Division of labor with the string suites (test_worker.py, test_exit_contract.py,
test_catalog_agents.py): those hold constants in sync across files; this harness
exercises the branches between them - the parks, the retries, the gate transaction. It
runs the unedited script: a fake ``claude`` and ``gh`` first on PATH, a local bare
repository standing in for GitHub (an isolated global gitconfig rewrites the script's
credential-free clone URL to it via ``url.insteadOf``, so the script needs no
test-only code path), and the REAL vendored stamp helper closing the gate. Each case
asserts the exit code the executor reacts to and what the origin's refs durably hold
afterwards.

The script's only test seam is ``FC_WORK_DIR`` (the workspace root, ``/work`` in a pod).

Requirements: a POSIX bash and git, which the suite needs anyway. The entrypoint's own
``jq`` (a worker-image runtime dependency) is used by the step-8 PR matching; those
cases skip where jq is absent, and a swallow-everything ``jq`` stub then keeps the
narration pipeline from breaking the ``tee`` capture mid-write.
"""
from __future__ import annotations

import json
from dataclasses import replace
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from pytest_intent import intent
from orchestrator.adapters.outbound.records.lifecycle_codec import encode_lifecycle
from orchestrator.adapters.outbound.records.yaml_record_parser import parse_record
from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.delivery import AWAITING_GATE
from orchestrator.domain.services.delivery_controls import derive_delivery_controls
from orchestrator.domain.services.delivery_resolution import derive_from_records
from orchestrator.domain.services.run_policy import _STAMP_REFUSED_EXIT

from test_worker import posix_bash

_ROOT = Path(__file__).resolve().parents[1]
_ENTRYPOINT = _ROOT / "devops" / "worker-entrypoint.sh"
_STAMP_HELPER = _ROOT / "devops" / "vendor" / "stamp_gate.py"
_RECORD_RUN_HELPER = _ROOT / "devops" / "record_run.py"
_APPROVER = _ROOT / "devops" / "approver.py"

BASH = posix_bash()
HAS_JQ = shutil.which("jq") is not None

pytestmark = pytest.mark.skipif(BASH is None, reason="no working POSIX bash on this host")

_SCRATCH_REF = "delivery/test-line"
_ESTABLISH_SUBJECT = "delivery(scope): establish scratch"

_RECORD_AT_GATE = """---
phase: intent+plan
status: gate
gate: plan
signed: pending
reviewed:
finished:
---

# Build handoff

One focused change, tested.
"""

_RECORD_ABORTED = _RECORD_AT_GATE.replace("status: gate", "status: aborted")
_RECORD_MIDWRITE = _RECORD_AT_GATE.replace("status: gate", "status: in-progress")

_FAKE_CLAUDE = """#!/usr/bin/env bash
# Fake claude for test_entrypoint_execution.py: each case scripts the agent's observable
# moves through FAKE_* env vars, so no model is in the loop.
set -u
prompt=""
prev=""
for a in "$@"; do
  [ "$prev" = "-p" ] && prompt="$a"
  prev="$a"
done
# The phase's own fresh-eyes review rounds, as the adversarial-review skill leaves them:
# one artifact per round under .delivery/reviews/, FAIL rounds included. The entrypoint
# locates the newest; it never prompts for one (INT-FC-R150).
for slot in R1 R2 R10; do
  var="FAKE_REVIEW_${slot}"
  if [ -n "${!var:-}" ] && [ -n "${FC_RECORD:-}" ]; then
    mkdir -p .delivery/reviews
    printf '%s\\n' "${!var}" > ".delivery/reviews/${FC_RECORD%.md}-2026-09-06-${slot,,}.md"
  fi
done
if [ -n "${FAKE_RECORD_CONTENT:-}" ] && [ -n "${FC_RECORD:-}" ]; then
  printf '%s' "$FAKE_RECORD_CONTENT" > ".delivery/${FC_RECORD}"
  # The skills commit and push the record as they land it; a case that says so does the same.
  if [ -n "${FAKE_COMMIT_RECORD:-}" ]; then
    git -C .delivery add "${FC_RECORD}"
    git -C .delivery commit -q -m "delivery(${FC_PHASE}): record landed by the agent"
    git -C .delivery push -q origin "HEAD:refs/heads/${FC_SCRATCH_REF}"
  fi
fi
if [ -n "${FAKE_DROP_SENTINEL:-}" ]; then
  printf '%s\\n' "${FAKE_SENTINEL_BODY:-}" > "${FC_SIGNAL_DIR}/${FAKE_DROP_SENTINEL}"
fi
if [ -n "${FAKE_LAND_COMMIT:-}" ]; then
  git commit -q --allow-empty -m "$FAKE_LAND_COMMIT"
  git push -q origin HEAD
fi
if [ -n "${FAKE_DUMP_AGENT:-}" ]; then
  env > "${FC_WORK_DIR}/agent-env.txt"
  printf '%s\n' "$@" > "${FC_WORK_DIR}/agent-args.txt"
  # The agent's own git and gh, as its commands would reach them.
  printf 'url=https://github.com/%s.git\n\n' "${FC_REPO#https://github.com/}" | git credential fill > "${FC_WORK_DIR}/agent-git.txt" 2>/dev/null || true
  gh api user > /dev/null 2>&1 || true
fi
if [ -n "${FAKE_ASK:-}" ]; then
  # Put each ask to the approver exactly as the agent's MCP config launches it.
  cp "${FC_WORK_DIR}/mcp.json" "${FC_WORK_DIR}/agent-mcp.json"
  mapfile -t approver < <(jq -r '.mcpServers.approver | .command, .args[]' "${FC_WORK_DIR}/mcp.json" | tr -d '\\r')
  printf '%s\\n' "$FAKE_ASK" | "${approver[@]}" > "${FC_WORK_DIR}/approver-said.txt"
fi
if [ -n "${FAKE_DEMO_PROBE:-}" ]; then
  printf 'url=https://github.com/%s.git\n\n' "$FAKE_DEMO_PROBE" | git credential fill > "${FC_WORK_DIR}/agent-demo.txt" 2>/dev/null || true
fi
if [ -n "${FAKE_INSPECT_CHECKOUT:-}" ]; then
  {
    git remote -v
    git config --list --show-origin
    if [ -n "${FC_HOME_DIR:-}" ]; then git -C "$FC_HOME_DIR" remote -v; fi
  } > "${FC_WORK_DIR}/inspection.log"
  cat "${FC_WORK_DIR}/inspection.log" >&2
fi
printf '%s\\n' '{"type":"assistant","message":{"content":[{"type":"text","text":"[fake] worker turn"}]}}'
if [ -n "${FAKE_AGENT_SAYS:-}" ]; then printf '%s\\n' "$FAKE_AGENT_SAYS"; fi
# The stream's final result event, when a case hands one; absent, the stream ends without it.
if [ -n "${FAKE_RESULT_EVENT:-}" ]; then printf '%s\\n' "$FAKE_RESULT_EVENT"; fi
exit "${FAKE_AGENT_EXIT:-0}"
"""

_FAKE_GH = """#!/usr/bin/env bash
# Fake gh for test_entrypoint_execution.py: canned answers from FAKE_* env vars.
if [ -n "${FAKE_GH_SEEN:-}" ]; then printf '%s\n' "${GH_TOKEN:-}" >> "$FAKE_GH_SEEN"; fi
case "${1:-} ${2:-}" in
  "issue view") printf '%s\\n' "${FAKE_TICKET_LABELED:-false}" ;;
  "pr list")   printf '%s\\n' "${FAKE_PR_LIST:-[]}" ;;
  "pr view")   printf '%s\\n' "${FAKE_PR_VIEW:-}" ;;
esac
exit 0
"""

# Narration-only stand-in when no real jq exists: consume the stream, print nothing.
# The step-8 cases that need REAL jq semantics skip on those hosts, so this stub never
# decides a tested branch - it only keeps `tee` from dying on a broken pipe.
_FAKE_JQ = """#!/usr/bin/env bash
cat >/dev/null
exit 0
"""


class Harness:
    """One temp GitHub-of-one: an origin with a default branch and the line's scratch
    ref, fakes on PATH, and an isolated git identity. `run()` executes the entrypoint."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.work = tmp / "work"
        self.origin = tmp / "origin.git"
        fakebin = tmp / "bin"
        home = tmp / "home"
        for d in (self.work, fakebin, home):
            d.mkdir()

        env = os.environ.copy()
        for key in list(env):
            if key.startswith(("FC_", "FAKE_", "ANTHROPIC_")) or key in (
                "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "CLAUDE_CODE_OAUTH_TOKEN",
                "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "XDG_CONFIG_HOME",
            ):
                env.pop(key)
        gitconfig = home / ".gitconfig"
        env["HOME"] = home.as_posix()
        env["GIT_CONFIG_GLOBAL"] = gitconfig.as_posix()
        env["GIT_CONFIG_NOSYSTEM"] = "1"  # no autocrlf/credential-manager surprises
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        self.env = env

        # The identity for fixture commits, and the rewrite that makes the script's own
        # GitHub URL land on the local bare origin - the script is not edited.
        self._git("config", "--file", str(gitconfig), "user.name", "fixture")
        self._git("config", "--file", str(gitconfig), "user.email", "fixture@test.local")
        self._git("config", "--file", str(gitconfig), "init.defaultBranch", "main")
        self._git(
            "config", "--file", str(gitconfig),
            f"url.file:///{self.origin.as_posix()}.insteadOf",
            "https://github.com/acme/app.git",
        )

        seed = tmp / "seed"
        self._git("init", "-q", str(seed))
        (seed / "README.md").write_text("# app\n", encoding="utf-8", newline="\n")
        self._git("add", "README.md", cwd=seed)
        self._git("commit", "-q", "-m", "chore: init", cwd=seed)
        # The line's scratch: an orphan ref with records at the branch root, carrying the
        # journal the stamp helper refuses without (a phase-exit obligation).
        self._git("switch", "-q", "--orphan", _SCRATCH_REF, cwd=seed)
        (seed / "journal.md").write_text(
            "# Journal\n\nno lessons this phase\n", encoding="utf-8", newline="\n"
        )
        (seed / "request.md").write_text("build the thing\n", encoding="utf-8", newline="\n")
        self._git("add", "journal.md", "request.md", cwd=seed)
        self._git("commit", "-q", "-m", _ESTABLISH_SUBJECT, cwd=seed)
        # Back to main BEFORE the bare clone: the bare origin inherits seed's HEAD, and
        # that HEAD is what the entrypoint's clone checks out as the default branch.
        self._git("switch", "-q", "main", cwd=seed)
        self._git("clone", "-q", "--bare", str(seed), str(self.origin))
        self.source_revision = self._git("--git-dir", str(self.origin), "rev-parse", "refs/heads/main").strip()

        # The stamp helper runs as `python3`, which on a Windows host may be the
        # Microsoft Store stub; pin it to the interpreter running this suite instead.
        py3 = f'#!/usr/bin/env bash\nexec "{Path(sys.executable).as_posix()}" "$@"\n'
        for name, body in (("claude", _FAKE_CLAUDE), ("gh", _FAKE_GH), ("python3", py3)):
            script = fakebin / name
            script.write_text(body, encoding="utf-8", newline="\n")
            os.chmod(script, 0o755)
        if not HAS_JQ:
            script = fakebin / "jq"
            script.write_text(_FAKE_JQ, encoding="utf-8", newline="\n")
            os.chmod(script, 0o755)

    def _git(self, *args: str, cwd: Path | None = None) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=cwd or self.tmp, env=self.env, capture_output=True, text=True, timeout=60
        )
        assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
        return proc.stdout

    def run(self, **fc: str) -> subprocess.CompletedProcess:
        env = dict(
            self.env,
            FC_REPO="https://github.com/acme/app",
            FC_GIT_TOKEN="t0k3n",
            FC_SKILL="test-skill",
            FC_SOURCE_REVISION=self.source_revision,
            FC_RECORD="",  # always defined: the script reads it unguarded under set -u
            FC_LIFECYCLE_DEFINITION=json.dumps(encode_lifecycle(CURRENT_LIFECYCLE)),
            FC_WORK_DIR=self.work.as_posix(),
            FC_STAMP_HELPER=_STAMP_HELPER.as_posix(),
            FC_RECORD_RUN_HELPER=_RECORD_RUN_HELPER.as_posix(),
            FC_APPROVER=_APPROVER.as_posix(),
            # The step's output, per case rather than the pod's shared /tmp path.
            FC_REFUSAL_FILE=(self.tmp / "fc-refusal").as_posix(),
        )
        env.update(fc)
        definition = json.loads(env["FC_LIFECYCLE_DEFINITION"]) if env["FC_LIFECYCLE_DEFINITION"] else {"phases": []}
        env.setdefault("FC_ARTIFACT", next((phase["artifact"] or "record" for phase in definition["phases"] if phase["record"] == env["FC_RECORD"]), ""))
        return subprocess.run(
            [BASH, str(_ENTRYPOINT), "run the phase"],
            capture_output=True, text=True, env=env, timeout=240,
        )

    # -- what the step reports back to the executor (its output parameter) ----------

    def output(self, name: str) -> str | None:
        path = self.tmp / f"fc-{name}"
        return path.read_text(encoding="utf-8") if path.exists() else None

    # -- what the origin durably holds afterwards ------------------------------------

    def scratch_file(self, path: str) -> str:
        return self._git("--git-dir", str(self.origin), "show", f"refs/heads/{_SCRATCH_REF}:{path}")

    def scratch_files(self) -> str:
        return self._git("--git-dir", str(self.origin), "ls-tree", "-r", "--name-only", _SCRATCH_REF)

    def scratch_subject(self) -> str:
        return self._git("--git-dir", str(self.origin), "log", "-1", "--format=%s", _SCRATCH_REF).strip()


@pytest.fixture
def harness(tmp_path):
    return Harness(tmp_path)


def _delivery(harness: Harness, **extra: str) -> subprocess.CompletedProcess:
    fc = dict(
        FC_PHASE="intent+plan",
        FC_RECORD="handoff.md",
        FC_SCRATCH_REF=_SCRATCH_REF,
    )
    fc.update(extra)
    return harness.run(**fc)


@intent("INT-FC-R162", "INT-FC-R129", "INT-FC-R89")
@pytest.mark.parametrize("checkout", ["ordinary", "managed-maintenance", "managed-delivery"])
@pytest.mark.parametrize("agent_exit", ["0", "1"])
def test_checkout_credentials_stay_out_of_config_arguments_and_retained_output(
    harness: Harness, checkout: str, agent_exit: str,
) -> None:
    own_token, pair_token = "sentinel-owned-credential", "sentinel-pair-credential"
    harness._git(
        "config", "--global", "--add", f"url.file:///{harness.origin.as_posix()}.insteadOf",
        "https://github.com/partner/home.git",
    )
    # Record the worker's real git arguments, then delegate to the real executable.
    real_git = Path(shutil.which("git")).as_posix()
    wrapper = harness.tmp / "bin" / "git"
    wrapper.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" >> "$FC_WORK_DIR/git-arguments.log"\n'
        f'exec "{real_git}" "$@"\n', encoding="utf-8", newline="\n",
    )
    os.chmod(wrapper, 0o755)
    startup = harness.tmp / "bash-env"
    startup.write_text(f'git() {{ "{wrapper.as_posix()}" "$@"; }}\n', encoding="utf-8", newline="\n")
    inputs = dict(
        FC_PHASE="maintenance:reconcile-docs", FC_GIT_USER="Foundry Review",
        FC_GIT_TOKEN=own_token + "\n", FC_PAIR_TOKEN=pair_token,
        FC_PAIR_REPO="partner/home", FAKE_INSPECT_CHECKOUT="1", FAKE_AGENT_EXIT=agent_exit,
        BASH_ENV=startup.as_posix(),
    )
    if checkout != "ordinary":
        inputs["FC_HOME_BRANCH"] = "main"
    if checkout == "managed-delivery":
        inputs.update(FC_PHASE="intent+plan", FC_RECORD="handoff.md", FC_SCRATCH_REF=_SCRATCH_REF)
    proc = harness.run(**inputs)
    expected = 1 if agent_exit == "1" else (64 if checkout == "managed-delivery" else 0)
    assert proc.returncode == expected, proc.stderr + proc.stdout
    # These bytes are the same checkout inspection a reviewer can retain in a transcript.
    retained = proc.stdout + proc.stderr + (harness.work / "inspection.log").read_text()
    retained += (harness.work / "git-arguments.log").read_text()
    retained += Path(harness.env["GIT_CONFIG_GLOBAL"]).read_text()
    for clone in (harness.work / "repo", harness.work / "home"):
        if clone.exists():
            config = (clone / ".git" / "config").read_text()
            assert "https://github.com/" in config
            assert "x-access-token:" not in config
            retained += config
    for helper in (harness.work / "git" / "credential-helper.sh", harness.work / "pair" / "credential-helper.sh"):
        retained += helper.read_text()
    assert own_token not in retained and pair_token not in retained


@intent("INT-FC-R162", "INT-FC-R129")
@pytest.mark.parametrize("assigned", ["both", "own", "pair", "neither"])
def test_git_supplies_only_the_grant_for_the_exact_repository(harness: Harness, assigned: str) -> None:
    own_token = "sentinel-owned-credential" if assigned in ("both", "own") else ""
    pair_token = "sentinel-pair-credential" if assigned in ("both", "pair") else ""
    proc = harness.run(
        FC_PHASE="maintenance:reconcile-docs", FC_GIT_TOKEN=own_token,
        FC_PAIR_TOKEN=pair_token, FC_PAIR_REPO="partner/home",
    )
    assert proc.returncode == 0, proc.stderr
    # The helpers read their grants from their files, so git authenticates with no token in the
    # environment it was started from (INT-FC-R192).
    env = dict(harness.env, FC_REPO="acme/app", FC_PAIR_REPO="partner/home", GIT_TERMINAL_PROMPT="0",
               FC_GIT_TOKEN_FILE=(harness.work / "git" / "token").as_posix(),
               FC_PAIR_TOKEN_FILE=(harness.work / "pair" / "token").as_posix())
    for name in ("FC_GIT_TOKEN", "FC_PAIR_TOKEN", "GH_TOKEN"):
        env.pop(name, None)
    for url, token in (
        ("https://github.com/acme/app.git", own_token),
        ("https://github.com/acme/app", own_token),
        ("https://github.com/partner/home.git", pair_token),
        ("https://github.com/partner/home", pair_token),
        ("https://github.com/acme/app.git/other", None),
        ("https://github.com/acme/app/other", None),
        ("https://github.com/partner/home.git/other", None),
        ("https://github.com/partner/home/other", None),
        ("https://github.com/acme/other.git", None),
        ("https://git.example/acme/app.git", None),
        ("http://github.com/acme/app.git", None),
    ):
        filled = subprocess.run(
            ["git", "credential", "fill"], input=f"url={url}\n\n", env=env,
            capture_output=True, text=True, timeout=30,
        )
        if not token:
            assert filled.returncode != 0 and not filled.stdout
            assert "sentinel-owned-credential" not in filled.stderr
            assert "sentinel-pair-credential" not in filled.stderr
        else:
            assert filled.returncode == 0, filled.stderr
            assert filled.stdout.splitlines()[-2:] == ["username=x-access-token", f"password={token}"]
    # Helpers implement the get operation only; git cannot persist either grant via them.
    for kind in ("git", "pair"):
        if not (harness.work / kind / "credential-helper.sh").exists():
            continue
        for operation in ("store", "erase"):
            ignored = subprocess.run(
                [BASH, str(harness.work / kind / "credential-helper.sh"), operation],
                input=f"password={own_token}\n\n", env=env, capture_output=True, text=True, timeout=30,
            )
            assert ignored.returncode == 0 and not ignored.stdout and not ignored.stderr


@intent("INT-FC-R192")
@pytest.mark.parametrize("gateway", [False, True])
def test_no_secret_reaches_the_agents_environment_and_its_git_and_gh_still_authenticate(
    harness: Harness, gateway: bool,
) -> None:
    """An agent's `env | grep ^FC_` printed the git token and the model credential into its
    transcript (#180). The agent now starts without either in its environment; its git reads the
    grant through the helper's file and its gh through the wrapper, and a gateway key reaches the
    CLI through apiKeyHelper rather than ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN."""
    own, model, pair = "sentinel-owned-credential", "sentinel-model-credential", "sentinel-pair-credential"
    seen = harness.tmp / "gh-seen.txt"
    extra = {"FC_BASE_URL": "https://gateway.example/v1"} if gateway else {}
    studio = "sentinel-studio-password"
    proc = harness.run(
        FC_PHASE="maintenance:reconcile-docs", FC_GIT_TOKEN=own, FC_MODEL_CREDENTIAL=model,
        FC_PAIR_TOKEN=pair, FC_PAIR_REPO="partner/home", FAKE_DUMP_AGENT="1",
        FAKE_GH_SEEN=seen.as_posix(), FC_MCP_ENDPOINTS="playbook-studio", FC_DOMAIN="example.test",
        FC_MCP_PLAYBOOK_STUDIO_USER="agent", FC_MCP_PLAYBOOK_STUDIO_PASS=studio, **extra,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    agent_env = dict(
        line.split("=", 1) for line in (harness.work / "agent-env.txt").read_text().splitlines() if "=" in line
    )
    for name in ("FC_GIT_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "FC_PAIR_TOKEN", "FC_MODEL_CREDENTIAL",
                 "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        assert name not in agent_env, name
    assert "FC_MCP_PLAYBOOK_STUDIO_PASS" not in agent_env
    leaked = {name for name, value in agent_env.items() if own in value or pair in value or studio in value}
    assert not leaked, leaked
    # The studio's password still reaches the CLI, in its MCP config's header.
    assert "FC_MCP_PLAYBOOK_STUDIO_USER" in agent_env
    # The subscription token is the CLI's own; the CLI keeps it from the commands it runs.
    assert {name for name, value in agent_env.items() if model in value} == {"CLAUDE_CODE_OAUTH_TOKEN"}
    # The agent's own git and gh still act as this phase's identity.
    assert (harness.work / "agent-git.txt").read_text().splitlines()[-1] == f"password={own}"
    assert own in seen.read_text().splitlines()
    args = (harness.work / "agent-args.txt").read_text()
    key = harness.work / "model" / "key"
    if gateway:
        assert f'{{"apiKeyHelper": "cat {key.as_posix()}"}}' in args
        assert key.read_text() == model and (key.stat().st_mode & 0o077) == 0
    else:
        assert "apiKeyHelper" not in args and not key.exists()
    for token_file in (harness.work / "git" / "token", harness.work / "pair" / "token"):
        assert (token_file.stat().st_mode & 0o077) == 0
    assert own not in proc.stdout + proc.stderr and model not in proc.stdout + proc.stderr


@intent("INT-FC-R162", "INT-FC-R192")
@pytest.mark.parametrize("demo_of, probe, answered", [
    ("acme/demo-source", "acme/demo-source", True),
    ("other-org/demo-source", "other-org/demo-source", False),
    ("acme/demo-source", "acme/unrelated", False),
    ("", "acme/demo-source", False),
])
def test_a_demo_lines_source_of_the_same_owner_authenticates_through_the_helper(
    harness: Harness, demo_of: str, probe: str, answered: bool,
) -> None:
    """A demo line reads its source over git, and the source's URL no longer finds a token in
    the environment; the helper answers for that exact repository when it shares our owner, and
    for no other. Probed from the agent's own environment, as the entrypoint left it."""
    own = "sentinel-owned-credential"
    proc = harness.run(FC_PHASE="maintenance:reconcile-docs", FC_GIT_TOKEN=own, FC_DEMO_OF=demo_of,
                       FAKE_DEMO_PROBE=probe)
    assert proc.returncode == 0, proc.stderr
    filled = (harness.work / "agent-demo.txt").read_text()
    if answered:
        assert filled.splitlines()[-1] == f"password={own}"
    else:
        assert own not in filled


@intent("INT-FC-R193")
@pytest.mark.parametrize("mode", ["bypassPermissions", "default"])
def test_the_log_names_the_session_each_failed_call_and_each_denial_masking_every_credential(
    harness: Harness, mode: str,
) -> None:
    """A run stopped three times on a refused git push, and neither the pod log nor the snapshot
    could show the refusal: the filter dropped tool results, the init event and the result's
    permission_denials (#169). Real CLI 2.1.293 event shapes; a failed call carries a credential
    the pod holds, which the log must never print."""
    if shutil.which("jq") is None:
        pytest.skip("the narration filter needs a real jq")
    own, model = "sentinel-owned-credential", "sentinel-model-credential"
    events = [
        '{"type":"system","subtype":"init","model":"claude-sonnet-5-5","permissionMode":"%s","claude_code_version":"2.1.293","mcp_servers":[{"name":"platform-studio","status":"connected"}]}' % mode,
        '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"toolu_a","name":"Bash","input":{"command":"git push","description":"push the record"}}]}}',
        json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_a", "is_error": True, "content": f"Exit code 1\nremote: Invalid username or password for {own} and {model}"}]}}),
        # A credential that straddles the line's cut must be masked whole, never cut to a prefix.
        json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_a", "is_error": True, "content": [{"type": "text", "text": "x" * 185 + own + " tail"}]}]}}),
        # One malformed event is dropped, and the narration carries on past it.
        '{"type":"result","permission_denials":[{"tool_name":"Bash","tool_input":"git status"}],"subtype":"error_during_execution"}',
        '{"type":"assistant","message":{"content":[{"type":"text","text":"after the odd event"}]}}',
        '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_a","is_error":false,"content":"fine"}]}}',
        json.dumps({"type": "result", "subtype": "success", "num_turns": 2, "permission_denials": [{"tool_name": "Bash", "tool_use_id": "toolu_b", "tool_input": {"command": "git push origin HEAD"}}]}),
    ]
    proc = harness.run(
        FC_PHASE="maintenance:reconcile-docs", FC_GIT_TOKEN=own, FC_MODEL_CREDENTIAL=model,
        FAKE_AGENT_SAYS="\n".join(events),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    log = proc.stdout
    assert f"[session] claude 2.1.293, model claude-sonnet-5-5, permission mode {mode}, mcp platform-studio:connected" in log
    warned = "[session] WARNING: permission mode default, not bypassPermissions" in log
    assert warned == (mode != "bypassPermissions")
    assert "[tool] Bash - push the record" in log
    assert "[tool error] Bash - Exit code 1 remote: Invalid username or password for *** and ***" in log
    assert log.count("[tool error]") == 2
    assert own[:8] not in log
    assert "after the odd event" in log
    assert "[denied] Bash: git push origin HEAD" in log
    assert "[agent done] success" in log
    assert own not in log + proc.stderr and model not in log + proc.stderr


@intent("INT-FC-R195")
def test_every_ask_goes_to_the_approver_and_each_answer_is_logged_masked(harness: Harness) -> None:
    """A key whose organisation policy turns bypass off ran sessions where every ask was refused,
    with nobody to answer it (#169); the prompt tool is the one door such a policy honours (#212).
    The fake agent launches the approver from the MCP config the worker wrote and asks it twice;
    one ask carries a credential the pod holds, which the log must never print."""
    if shutil.which("jq") is None:
        pytest.skip("the approver's config and log lines need a real jq")
    own = "sentinel-owned-credential"
    asks = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "approve", "arguments": {"tool_name": "Bash", "input": {"command": f"git push https://x:{own}@github.com/acme/app HEAD"}}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "approve", "arguments": {"tool_name": "Write", "input": {"file_path": "notes.md", "content": "hi"}}}},
    ]
    proc = harness.run(
        FC_PHASE="maintenance:reconcile-docs", FC_GIT_TOKEN=own, FAKE_DUMP_AGENT="1",
        FAKE_ASK="\n".join(json.dumps(a) for a in asks),
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    args = (harness.work / "agent-args.txt").read_text(encoding="utf-8").splitlines()
    assert args[args.index("--permission-prompt-tool") + 1] == "mcp__approver__approve"
    config = json.loads((harness.work / "agent-mcp.json").read_text(encoding="utf-8"))
    assert config["mcpServers"]["approver"]["type"] == "stdio"
    said = [json.loads(line) for line in (harness.work / "approver-said.txt").read_text(encoding="utf-8").splitlines()]
    assert [json.loads(r["result"]["content"][0]["text"])["behavior"] for r in said[1:]] == ["allow", "allow"]
    log = proc.stdout
    assert "[approved] Bash: git push https://x:***@github.com/acme/app HEAD" in log
    assert "[approved] Write: notes.md" in log
    assert own not in log + proc.stderr


@intent("INT-FC-R162")
def test_failed_clone_diagnostics_keep_the_checkout_token_out(harness: Harness) -> None:
    # The actual clone fails at its repository transport before any agent is launched.
    harness.origin.rename(harness.tmp / "unreachable.git")
    token = "sentinel-failed-checkout-credential"
    proc = harness.run(FC_PHASE="maintenance:reconcile-docs", FC_GIT_TOKEN=token)
    assert proc.returncode != 0 and "fatal:" in proc.stderr
    assert token not in proc.stdout + proc.stderr
    assert token not in Path(harness.env["GIT_CONFIG_GLOBAL"]).read_text()
    assert token not in (harness.work / "git" / "credential-helper.sh").read_text()
    assert not (harness.work / "repo").exists()


# --- the gate transaction (step 5): review, stamp, push -------------------------------


@intent("INT-FC-R52")
@intent('INT-FC-R18', 'INT-FC-R21')
def test_one_shot_stamps_a_passing_gate_and_pushes_the_evidence(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: the plan traces.\n\n**VERDICT: PASS**\n\nSolid.",
    )
    assert proc.returncode == 0, proc.stderr
    assert "gate stamped" in proc.stdout
    assert "gate evidence is .delivery/reviews/handoff-2026-09-06-r1.md" in proc.stdout
    record = harness.scratch_file("handoff.md")
    assert re.search(r"signed:\s*\d{4}-\d{2}-\d{2}", record)  # the stamp, not pending
    assert "status: complete" in record
    # The stamp's two closure fields, written in the same act as the signature: the moment,
    # and how the gate closed - a first round that passed on a first attempt.
    assert re.search(r"^signed_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", record, re.MULTILINE)
    assert "outcome: as it stood" in record
    # The review's verbatim output rides the same ref as the record it authorizes.
    assert re.search(r"^reviews/handoff-.*\.md$", harness.scratch_files(), re.MULTILINE)


@intent("INT-FC-R167", "INT-FC-R21")
@pytest.mark.parametrize("missing", ["FC_LIFECYCLE_DEFINITION", "FC_ARTIFACT"])
def test_delivery_record_requires_captured_handler_context_before_checkout(harness, missing):
    proc = _delivery(harness, **{missing: ""})
    assert proc.returncode != 0
    assert not (harness.work / "repo").exists()


@intent("INT-FC-R167", "INT-FC-R21")
def test_renamed_managed_home_build_gate_keeps_signature_pending(harness):
    harness._git("config", "--global", "--add", f"url.file:///{harness.origin.as_posix()}.insteadOf", "https://github.com/partner/home.git")
    initial = CURRENT_LIFECYCLE
    phases = list(initial.phases)
    build_index = next(i for i, phase in enumerate(phases) if phase.artifact == "build")
    old_name = phases[build_index].name
    phases[build_index] = replace(phases[build_index], name="release", record="release.md", gate="release-approval")
    for i in range(build_index + 1, len(phases)):
        phases[i] = replace(phases[i], inputs=tuple("release" if name == old_name else name for name in phases[i].inputs))
    definition = replace(initial, version="1.1.0", phases=tuple(phases))
    body = _RECORD_AT_GATE.replace("phase: intent+plan", "phase: release").replace("gate: plan", "gate: release-approval")
    proc = harness.run(FC_PHASE="release", FC_RECORD="release.md", FC_GATE="release-approval", FC_MODE="one-shot", FC_SCRATCH_REF=_SCRATCH_REF, FC_HOME_BRANCH="main", FC_PAIR_REPO="partner/home", FC_PAIR_TOKEN="foreign-token", FC_LIFECYCLE_DEFINITION=json.dumps(encode_lifecycle(definition)), FAKE_RECORD_CONTENT=body, FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    record = harness.scratch_file("release.md")
    assert "signed: pending" in record
    assert re.search(r"reviewed:\s*\d{4}-\d{2}-\d{2}", record)
    assert "reviews/release-2026-09-06-r1.md" in harness.scratch_files()


@intent("INT-FC-R52")
@intent('INT-FC-R18', 'INT-FC-R21')
def test_interactive_records_the_review_and_leaves_the_gate_for_its_signer(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    assert proc.returncode == 0, proc.stderr
    assert "gate awaits the human signature" in proc.stdout
    record = harness.scratch_file("handoff.md")
    assert "signed: pending" in record  # the human's act, not the worker's
    assert re.search(r"reviewed:\s*\d{4}-\d{2}-\d{2}", record)


@intent("INT-FC-R52")
@intent('INT-FC-R17', 'INT-FC-R18')
def test_a_failing_review_fails_the_attempt_and_stamps_nothing(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: a traceability gap.\n\n**VERDICT: FAIL**",
    )
    assert proc.returncode == 1
    assert "did not pass" in proc.stderr
    # No stamp left the pod, but the evidence did: the failing round rides the scratch ref
    # so the retried phase reads it as its prior, and the record stays pending.
    assert harness.scratch_subject() == "delivery(intent+plan): failing fresh-eyes review kept as evidence"
    assert re.search(r"^reviews/handoff-2026-09-06-r1\.md$", harness.scratch_files(), re.MULTILINE)
    assert "signed: pending" in harness.scratch_file("handoff.md")


@intent("INT-FC-R150")
def test_a_record_at_its_gate_with_no_review_fails_the_attempt(harness):
    proc = _delivery(harness, FC_GATE="plan", FC_MODE="one-shot", FAKE_RECORD_CONTENT=_RECORD_AT_GATE)
    assert proc.returncode == 1
    assert "no fresh-eyes review for handoff.md" in proc.stderr
    # The unreviewed record is pushed as it stands, unstamped, for the retry to read.
    assert "signed: pending" in harness.scratch_file("handoff.md")


@intent("INT-FC-R150")
def test_the_gate_closes_over_the_newest_round_not_the_first(harness):
    # Round 1 failed, the phase fixed and re-reviewed, round 2 passed: both artifacts sit
    # under .delivery/reviews/, and the gate reads the newest.
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: a gap.\n\n**VERDICT: FAIL**",
        FAKE_REVIEW_R2="Round 1's blocker is closed.\n\n**VERDICT: PASS**",
    )
    assert proc.returncode == 0, proc.stderr
    assert "gate evidence is .delivery/reviews/handoff-2026-09-06-r2.md" in proc.stdout
    files = harness.scratch_files()
    assert re.search(r"^reviews/handoff-2026-09-06-r1\.md$", files, re.MULTILINE)  # the FAIL round survives
    assert re.search(r"^reviews/handoff-2026-09-06-r2\.md$", files, re.MULTILINE)
    record = harness.scratch_file("handoff.md")
    assert re.search(r"signed:\s*\d{4}-\d{2}-\d{2}", record)
    # A FAIL round before the passing one is how the stamp derives the closure's outcome.
    assert "outcome: re-driven" in record


@intent("INT-FC-R150")
def test_newest_means_version_order_so_round_ten_follows_round_two(harness):
    # Lexically r10 sorts before r2; the gate must read r10 (the real newest), which failed.
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R2="Findings: none.\n\n**VERDICT: PASS**",
        FAKE_REVIEW_R10="A regression since round 2.\n\n**VERDICT: FAIL**",
    )
    assert proc.returncode == 1
    assert "handoff-2026-09-06-r10.md" in proc.stderr and "did not pass" in proc.stderr
    assert "signed: pending" in harness.scratch_file("handoff.md")


# --- self-validation (steps 4 and 7): the record's work-truth decides the exit --------


@intent("INT-FC-R50")
@intent('INT-FC-R19', 'INT-FC-R20')
def test_a_clean_agent_exit_with_no_record_is_a_deliberate_park_not_a_retry(harness):
    proc = _delivery(harness)  # the fake writes nothing and exits 0
    assert proc.returncode == 64
    assert "not written" in proc.stderr and "not retrying" in proc.stderr


@intent("INT-FC-R50")
@intent('INT-FC-R19')
def test_a_record_stamped_aborted_parks_degraded_after_pushing_it(harness):
    proc = _delivery(harness, FAKE_RECORD_CONTENT=_RECORD_ABORTED)
    assert proc.returncode == 64
    assert "status: aborted" in proc.stderr
    # The park is TERMINAL but the evidence still lands: the aborted record is pushed
    # (step 6 runs before step 7's exit), so the human who clears the wall can read it.
    assert "status: aborted" in harness.scratch_file("handoff.md")


@intent("INT-FC-R50")
@intent('INT-FC-R19', 'INT-FC-R20')
def test_a_mid_write_record_is_transient_and_retried(harness):
    proc = _delivery(harness, FAKE_RECORD_CONTENT=_RECORD_MIDWRITE)
    assert proc.returncode == 1
    assert "not complete" in proc.stderr and "retrying" in proc.stderr


@pytest.mark.parametrize("status_line", ["", "status: []", "status: unsupported"])
@intent('INT-FC-R20')
def test_a_phase_record_without_supported_status_is_transient(harness, status_line):
    record = _RECORD_AT_GATE.replace("status: gate", status_line)
    proc = _delivery(harness, FAKE_RECORD_CONTENT=record)
    assert proc.returncode == 1
    assert "not complete" in proc.stderr and "retrying" in proc.stderr
    assert "legacy" not in proc.stderr.lower()
    persisted = harness.scratch_file("handoff.md")
    assert "One focused change, tested." in persisted
    assert "signed: pending" in persisted


def test_learn_with_a_stamped_journal_and_no_phase_record_completes(harness):
    seed = harness.tmp / "seed"
    harness._git("switch", "-q", _SCRATCH_REF, cwd=seed)
    (seed / "journal.md").write_text("---\nlearned: 2026-10-05\n---\n\n# Journal\n", encoding="utf-8", newline="\n")
    harness._git("add", "journal.md", cwd=seed)
    harness._git("commit", "-q", "-m", "delivery(learn): journal", cwd=seed)
    harness._git("push", "-q", str(harness.origin), _SCRATCH_REF, cwd=seed)
    proc = harness.run(FC_PHASE="learn", FC_RECORD="", FC_SCRATCH_REF=_SCRATCH_REF)
    assert proc.returncode == 0, proc.stderr
    assert "learned: 2026-10-05" in harness.scratch_file("journal.md")


# --- the terminal parks (steps 3a-3c) --------------------------------------------------


@intent("INT-FC-R117")
def test_the_models_session_wall_parks_terminal_instead_of_burning_the_budget(harness):
    proc = harness.run(
        FC_PHASE="scope",
        FAKE_AGENT_EXIT="1",
        FAKE_AGENT_SAYS="You've reached your Fable 5 limit. /model to switch models.",
    )
    assert proc.returncode == 67
    assert "session-limit stop" in proc.stderr


@intent("INT-FC-R99")
def test_a_delivery_scale_punt_parks_65_when_the_label_authorizes_it(harness):
    proc = harness.run(
        FC_PHASE="maintenance:reconcile-docs",
        FC_TICKET="7",
        FAKE_DROP_SENTINEL=".foundry-delivery-scale",
        FAKE_TICKET_LABELED="true",
    )
    assert proc.returncode == 65
    assert "delivery-scale stop" in proc.stderr


@intent("INT-FC-R99")
def test_a_sentinel_without_the_ticket_label_is_contamination_not_a_park(harness):
    # The file says "park"; GitHub records no punt. A run that may have done real work
    # must not park for a reason that never happened - it falls through to the ordinary
    # contracts and completes.
    proc = harness.run(
        FC_PHASE="maintenance:reconcile-docs",
        FC_TICKET="7",
        FAKE_DROP_SENTINEL=".foundry-delivery-scale",
        FAKE_TICKET_LABELED="false",
    )
    assert proc.returncode == 0, proc.stderr
    assert "complete" in proc.stdout


# --- the maintenance completeness contract (step 8): green means it shipped -----------


@intent("INT-FC-R84")
@pytest.mark.skipif(not HAS_JQ, reason="the entrypoint's PR matching runs local jq")
def test_a_gated_resolve_that_opened_no_pr_never_reads_green(harness):
    proc = harness.run(FC_PHASE="maintenance:resolve", FC_TICKET="7", FAKE_PR_LIST="[]")
    assert proc.returncode == 1
    assert "left NO open PR" in proc.stderr


@intent("INT-FC-R84")
@pytest.mark.skipif(not HAS_JQ, reason="the entrypoint's PR matching runs local jq")
def test_a_gated_resolve_is_proven_by_the_pr_that_matches_the_shared_rule(harness):
    proc = harness.run(
        FC_PHASE="maintenance:resolve",
        FC_TICKET="7",
        FAKE_PR_LIST='[{"number":9,"headRefName":"fix/7-thing",'
                     '"title":"fix(#7): thing","body":"Closes #7"}]',
    )
    assert proc.returncode == 0, proc.stderr
    assert "has an open PR" in proc.stdout


@intent("INT-FC-R85")
@pytest.mark.skipif(not HAS_JQ, reason="the entrypoint's review check runs local jq")
@pytest.mark.parametrize("ending", ["PASS", "FAIL", "UNRECORDED"])
def test_a_review_is_proven_by_any_of_review_prs_three_endings(harness, ending):
    # UNRECORDED is a completed review whose identity could record neither PASS nor FAIL:
    # the act is done, so the run completes rather than retrying into a Failed run.
    body = f"Findings: none.\n\n**VERDICT: {ending}**"
    proc = harness.run(
        FC_PHASE="maintenance:review",
        FC_TICKET="12",
        FAKE_PR_VIEW=json.dumps({"reviews": [{"body": body}]}),
    )
    assert proc.returncode == 0, proc.stderr
    assert "review posted a VERDICT on PR #12" in proc.stdout


@intent("INT-FC-R85")
@pytest.mark.skipif(not HAS_JQ, reason="the entrypoint's review check runs local jq")
@pytest.mark.parametrize(
    "body", ["Looks reasonable, more later.", "VERDICT: pending, more later."]
)
def test_a_review_that_posted_no_verdict_never_reads_green(harness, body):
    # A VERDICT: line whose word is none of the three endings is no verdict either.
    proc = harness.run(
        FC_PHASE="maintenance:review",
        FC_TICKET="12",
        FAKE_PR_VIEW=json.dumps({"reviews": [{"body": body}]}),
    )
    assert proc.returncode == 1
    assert "review posted NO VERDICT on PR #12" in proc.stderr


@intent("INT-FC-R146")
def test_a_direct_resolve_is_proven_by_its_landed_commit(harness):
    proc = harness.run(
        FC_PHASE="maintenance:resolve",
        FC_TICKET="7",
        FC_MAINT_MODE="direct",
        FAKE_LAND_COMMIT="fix: the thing (#7)",
    )
    assert proc.returncode == 0, proc.stderr
    assert "landed a ticket-referencing commit" in proc.stdout


@intent("INT-FC-R146")
def test_a_direct_resolve_that_landed_nothing_fails_rather_than_reading_green(harness):
    proc = harness.run(FC_PHASE="maintenance:resolve", FC_TICKET="7", FC_MAINT_MODE="direct")
    assert proc.returncode == 1
    assert "left NO ticket-referencing commit" in proc.stderr


# --- the gate export (step 5): a tooled gate freezes its studio's deliverables ---------

_PROPOSAL_AT_GATE = """---
phase: scope
status: gate
gate: proposal
signed: pending
reviewed:
finished:
delivers: P1
---

# Proposal

P1 scoped.
"""


# The phase's project activities, in the shape the stamp sums per stream (a `Stream` and an
# `Effort (MD)` column, REF-Estimatekit section 2): the effort table the proposal stamp
# appends to the record is read off exactly this file.
_PROJECT_TSV = (
    "ID\tStream\tActivity\tEffort (MD)\n"
    "A1\tBuild Activities\tbuild the thing\t10\n"
    "A2\tProject Management\tsteer it\t2.5\n"
)


class _ToolStub(BaseHTTPRequestHandler):
    """A stand-in estimation instance answering the two reads the export makes, in the
    file shapes a real instance has (per-phase names under data/architecture/ and
    data/activities/)."""

    def log_message(self, *args: object) -> None:  # quiet
        pass

    def do_GET(self) -> None:  # noqa: N802 - http.server's own naming
        if self.path == "/api/projects/app/files":
            body: dict = {"files": [
                {"path": "data/architecture/P1-overview.puml", "name": "P1-overview.puml"},
                {"path": "data/architecture/P1-components.tsv", "name": "P1-components.tsv"},
                {"path": "data/assumptions/02-assumptions.tsv", "name": "02-assumptions.tsv"},
                {"path": "data/activities/P1-build.tsv", "name": "P1-build.tsv"},
                {"path": "data/activities/P1-project.tsv", "name": "P1-project.tsv"},
            ]}
        elif self.path.endswith("/files/data/activities/P1-project.tsv"):
            body = {"path": "data/activities/P1-project.tsv", "content": _PROJECT_TSV}
        elif self.path.startswith("/api/projects/app/files/"):
            body = {"path": self.path.split("/files/")[1], "content": "FIXTURE " + self.path}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def tool_stub():
    server = HTTPServer(("127.0.0.1", 0), _ToolStub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _scope(harness: Harness, **extra: str) -> subprocess.CompletedProcess:
    fc = dict(FC_PHASE="scope", FC_RECORD="proposal.md", FC_GATE="proposal", FC_SCRATCH_REF=_SCRATCH_REF)
    fc.update(extra)
    return harness.run(**fc)


@intent("INT-FC-R151")
def test_a_one_shot_proposal_stamp_freezes_the_estimation_export_over_the_tool_url(harness, tool_stub):
    proc = _scope(
        harness,
        FC_MODE="one-shot",
        FC_TOOL_URL=tool_stub,
        FC_SLUG="app",
        FAKE_RECORD_CONTENT=_PROPOSAL_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "gate stamped" in proc.stdout
    assert "Gate export (P1 from estimation project 'app'" in proc.stdout
    files = harness.scratch_files()
    # The frozen deliverables ride the scratch ref with the stamped record: the phase's
    # architecture, its assumptions, and its effort (the activity files verbatim).
    assert re.search(r"^architecture/P1-overview\.puml$", files, re.MULTILINE)
    assert re.search(r"^architecture/P1-components\.tsv$", files, re.MULTILINE)
    assert re.search(r"^assumptions/02-assumptions\.tsv$", files, re.MULTILINE)
    assert re.search(r"^estimate/P1-build\.tsv$", files, re.MULTILINE)
    assert re.search(r"^estimate/P1-project\.tsv$", files, re.MULTILINE)
    record = harness.scratch_file("proposal.md")
    assert re.search(r"signed:\s*\d{4}-\d{2}-\d{2}", record)
    # ...and the per-stream effort table the stamp appends to the record, summed from the
    # project activities, in the one shape the delivery analytics parse.
    assert "| Stream | Effort |" in record
    assert "| Build Activities | 10 MD |" in record and "| Project Management | 2.5 MD |" in record
    assert "| Total | 12.5 MD |" in record


@intent("INT-FC-R151", "INT-FC-R181")
def test_a_one_shot_stamp_that_refuses_stops_terminal_with_the_gate_signable(harness):
    # A tooled gate handed no tool URL: the stamper refuses the export, so it signs nothing.
    proc = _scope(
        harness,
        FC_MODE="one-shot",
        FAKE_RECORD_CONTENT=_PROPOSAL_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    # A wall no retry clears: the step ends on the stamp-refused exit, the code the compiled
    # retry expression excludes, and says why in the stamper's own words and what clears it.
    assert proc.returncode == _STAMP_REFUSED_EXIT, proc.stderr + proc.stdout
    refusal = harness.output("refusal")
    assert refusal is not None
    assert refusal.startswith(
        "worker: the proposal stamp refused over a passing review (REFUSED: no estimation instance to export from"
    )
    assert f"stamp-refused stop, not retrying (exit {_STAMP_REFUSED_EXIT})" in refusal
    assert refusal.rstrip().endswith("sign the proposal gate from the cockpit, then drive the line")
    assert refusal.strip() in proc.stderr  # the same words the log carries
    # The record reached the origin before the stop: the passing review recorded beside its
    # round, the signature left for the operator, the stamper's own refusal line on it.
    record = harness.scratch_file("proposal.md")
    assert "signed: pending" in record
    assert re.search(r"^reviewed: \d{4}-\d{2}-\d{2}$", record, re.MULTILINE)
    assert "status: gate" in record
    assert re.search(r"^reviews/proposal-.*\.md$", harness.scratch_files(), re.MULTILINE)
    fm = parse_record(record).frontmatter
    assert fm.stamp_refused.startswith("REFUSED: no estimation instance to export from")
    # The line the console derives from it is signable from the cockpit, and its next
    # command - what the delivery card shows - names the refusal.
    state = derive_from_records("acme/app", True, {"proposal.md": parse_record(record)})
    assert state.status == AWAITING_GATE and state.blocked_gate == "proposal"
    assert "proposal.md" in state.reviewed_records  # Sign's own precondition
    assert state.next_command.startswith(
        "sign the proposal gate (the one-shot stamp refused: REFUSED: no estimation instance"
    )
    # Beside the run the stop ended, the cockpit offers Sign.
    assert derive_delivery_controls(state.status, "delivery-acme-abc", "Failed", {}).can_sign


@intent("INT-FC-R181")
def test_a_stale_stamp_refusal_is_cleared_by_the_next_stamp_that_closes_it(harness, tool_stub):
    stale = _PROPOSAL_AT_GATE.replace(
        "delivers: P1\n", 'delivers: P1\nstamp_refused: "REFUSED: an earlier attempt"\n'
    )
    proc = _scope(
        harness,
        FC_MODE="one-shot",
        FC_TOOL_URL=tool_stub,
        FC_SLUG="app",
        FAKE_RECORD_CONTENT=stale,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    record = harness.scratch_file("proposal.md")
    assert re.search(r"signed:\s*\d{4}-\d{2}-\d{2}", record)
    assert "stamp_refused" not in record
    assert harness.output("refusal") is None  # a step that closed its gate stops on nothing


@intent("INT-FC-R182")
def test_a_stopping_step_reports_its_refusal_line_as_its_output(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: a gap.\n\nVERDICT: FAIL",
    )
    assert proc.returncode == 1
    refusal = harness.output("refusal")
    assert refusal is not None
    assert refusal.startswith("worker: fresh-eyes review did not pass the plan gate")
    assert refusal.strip() in proc.stderr  # the same words the log carries


@intent("INT-FC-R182")
def test_a_step_that_stops_without_a_line_of_its_own_still_reports_its_exit(harness):
    # A delivery step with no scratch ref stops on an explicit line; the trap's fallback
    # covers any exit that names nothing, so the output is never empty on a failure.
    proc = _delivery(harness, FC_SCRATCH_REF="")
    assert proc.returncode != 0
    assert harness.output("refusal")


@intent("INT-FC-R181")
def test_a_refusal_left_by_a_one_shot_stop_is_cleared_by_an_interactive_re_drive(harness):
    # A recovery path the stop leaves open: the line switched to interactive and re-driven.
    # That run met no refusal, so its record must name none.
    stale = _RECORD_AT_GATE.replace("gate: plan\n", 'gate: plan\nstamp_refused: "REFUSED: an earlier attempt"\n')
    proc = _delivery(harness, FC_GATE="plan", FAKE_RECORD_CONTENT=stale, FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    record = harness.scratch_file("handoff.md")
    assert "signed: pending" in record and "stamp_refused" not in record


def _fake_stamper(harness: Harness, body: str) -> str:
    script = harness.tmp / "fake_stamp_gate.py"
    script.write_text(body, encoding="utf-8", newline="\n")
    return script.as_posix()


@intent("INT-FC-R181")
def test_a_one_shot_stamp_that_fails_without_a_refusal_line_stays_transient(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        FC_STAMP_HELPER=_fake_stamper(harness, "import sys\nprint('Traceback: something broke')\nsys.exit(2)\n"),
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    # Not a refusal the stamper stated, so not the terminal stop: the executor retries.
    assert proc.returncode == 1
    assert harness.output("refusal").startswith("worker: the plan stamp exited 2 without a refusal line")


@intent("INT-FC-R181")
def test_a_refusal_that_also_refuses_the_review_fails_the_attempt_naming_both(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        # The stamp and the review-only call refuse for different reasons, so the line must
        # carry each call's own words.
        FC_STAMP_HELPER=_fake_stamper(
            harness,
            "import sys\n"
            "print('REFUSED: review not recorded' if '--review-only' in sys.argv else 'REFUSED: export refused')\n"
            "sys.exit(1)\n",
        ),
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    # No recorded review means no gate to sign, so not the terminal stop: the executor retries.
    assert proc.returncode == 1
    refusal = harness.output("refusal")
    assert "(REFUSED: export refused)" in refusal
    assert "recording its review refused too (REFUSED: review not recorded)" in refusal


@intent("INT-FC-R182")
def test_the_compiler_and_the_entrypoint_name_the_same_output_file():
    from orchestrator.adapters.outbound.argo.worker_template import REFUSAL_PATH

    script = _ENTRYPOINT.read_text(encoding="utf-8")
    assert f'FC_REFUSAL_FILE="${{FC_REFUSAL_FILE:-{REFUSAL_PATH}}}"' in script


# --- the run's figures (step 4c): what the run cost rides the record it produced ---------

_RESULT_EVENT = json.dumps({
    "type": "result", "subtype": "success", "is_error": False, "duration_ms": 754000,
    "num_turns": 12, "total_cost_usd": 0.4523,
    "usage": {
        "input_tokens": 1000, "output_tokens": 50,
        "cache_read_input_tokens": 20000, "cache_creation_input_tokens": 3000,
    },
    "modelUsage": {
        "claude-opus-4-1-20250805": {
            "inputTokens": 1000, "outputTokens": 50, "cacheReadInputTokens": 20000,
            "cacheCreationInputTokens": 3000, "webSearchRequests": 0, "costUSD": 0.4523,
            "contextWindow": 200000,
        },
    },
})

_STAMP_ISO = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"


@intent("INT-FC-R161")
def test_the_runs_figures_ride_the_same_push_as_its_stamped_record(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FC_MODE="one-shot",
        FC_RUN="delivery-app-x7k2p",
        FC_AGENT="planner",
        FC_MODEL="claude-opus-4-1",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
        FAKE_RESULT_EVENT=_RESULT_EVENT,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Run figures recorded in .delivery/handoff.md: 24050 tokens, 0.452300 USD, 12 turns" in proc.stdout
    record = harness.scratch_file("handoff.md")
    # The identity the console knows the run by, and who ran it with what.
    assert "run: delivery-app-x7k2p" in record
    assert "run_agent: planner" in record
    assert "run_model: claude-opus-4-1" in record
    # What it cost, every type summed and by type, and per model.
    assert "run_tokens: 24050" in record and "run_cost: 0.452300" in record and "run_turns: 12" in record
    assert "run_tokens_input: 1000" in record and "run_tokens_cache_read: 20000" in record
    assert "run_model_claude_opus_4_1_20250805_tokens: 24050" in record
    assert "run_model_claude_opus_4_1_20250805_cost: 0.452300" in record
    # The span, in the harness's own clock.
    assert re.search(rf"^run_started: {_STAMP_ISO}$", record, re.MULTILINE)
    assert re.search(rf"^run_finished: {_STAMP_ISO}$", record, re.MULTILINE)
    # ...and all of it in the frontmatter of the record the stamp closed, in one push.
    front = record.split("---", 2)[1]
    assert "run_tokens: 24050" in front
    assert re.search(r"signed:\s*\d{4}-\d{2}-\d{2}", front)
    assert harness.scratch_subject() == "delivery(intent+plan): test-skill"


@intent("INT-FC-R161")
def test_an_aborted_attempts_figures_still_land_with_its_record(harness):
    # A degraded stop cost what it cost; the figures ride the aborted record's push.
    proc = _delivery(
        harness, FC_RUN="delivery-app-x7k2p", FAKE_RECORD_CONTENT=_RECORD_ABORTED, FAKE_RESULT_EVENT=_RESULT_EVENT,
    )
    assert proc.returncode == 64
    record = harness.scratch_file("handoff.md")
    assert "status: aborted" in record and "run_tokens: 24050" in record and "run: delivery-app-x7k2p" in record


@intent("INT-FC-R161")
def test_a_failing_reviews_evidence_commit_carries_the_figures_too(harness):
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: a gap.\n\n**VERDICT: FAIL**",
        FAKE_RESULT_EVENT=_RESULT_EVENT,
    )
    assert proc.returncode == 1
    record = harness.scratch_file("handoff.md")
    assert "signed: pending" in record and "run_tokens: 24050" in record


@intent("INT-FC-R161")
def test_a_stream_with_no_result_event_records_nothing_and_never_fails_the_run(harness):
    # The fake prints no result event here: a malformed or truncated stream. The gate
    # transaction proceeds exactly as before and the record carries no figures.
    proc = _delivery(
        harness,
        FC_GATE="plan",
        FAKE_RECORD_CONTENT=_RECORD_AT_GATE,
        FAKE_REVIEW_R1="Findings: none.\n\n**VERDICT: PASS**",
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "no result event" in proc.stdout and "not recorded" in proc.stdout
    record = harness.scratch_file("handoff.md")
    assert "run_tokens" not in record and re.search(r"reviewed:\s*\d{4}-\d{2}-\d{2}", record)


@intent("INT-FC-R161")
@pytest.mark.parametrize(
    ("says", "code"),
    [("", 1), ("You've reached your Fable 5 limit. /model to switch models.", 67)],
    ids=["transient", "session-limit"],
)
def test_a_failed_turns_figures_land_on_the_record_the_agent_had_committed(harness, says, code):
    # The agent landed its record during the turn, then its turn failed: the attempt's spend
    # rides that committed record as one push, and the stop keeps its own exit code.
    proc = _delivery(
        harness,
        FC_RUN="delivery-app-x7k2p",
        FAKE_RECORD_CONTENT=_RECORD_MIDWRITE,
        FAKE_COMMIT_RECORD="1",
        FAKE_AGENT_EXIT="1",
        FAKE_AGENT_SAYS=says,
        FAKE_RESULT_EVENT=_RESULT_EVENT,
    )
    assert proc.returncode == code, proc.stderr
    record = harness.scratch_file("handoff.md")
    assert "status: in-progress" in record and "run: delivery-app-x7k2p" in record
    assert "run_tokens: 24050" in record and "run_cost: 0.452300" in record
    assert harness.scratch_subject() == "delivery(intent+plan): run figures of an attempt cut short"


@intent("INT-FC-R161")
def test_a_failed_turn_never_publishes_a_record_the_agent_left_uncommitted(harness):
    # The record is in the working tree only: the harness does not publish an agent's
    # uncommitted work at a failed turn, so nothing reaches the remote and the stop is unchanged.
    proc = _delivery(
        harness, FAKE_RECORD_CONTENT=_RECORD_MIDWRITE, FAKE_AGENT_EXIT="1", FAKE_RESULT_EVENT=_RESULT_EVENT,
    )
    assert proc.returncode == 1
    assert "uncommitted at this stop" in proc.stderr
    assert harness.scratch_subject() == _ESTABLISH_SUBJECT
    assert "handoff.md" not in harness.scratch_files()


@intent("INT-FC-R161")
def test_a_worker_with_no_record_says_its_figures_are_not_recorded(harness):
    proc = harness.run(FC_PHASE="maintenance:reconcile-docs", FC_TICKET="7", FAKE_RESULT_EVENT=_RESULT_EVENT)
    assert proc.returncode == 0, proc.stderr
    assert "leaves no record; the run's figures are not recorded" in proc.stdout


def test_mismatched_playbook_revision_refuses_before_clone_or_agent(harness):
    playbook = harness.tmp / "playbook"
    playbook.mkdir()
    (playbook / "REVISION").write_text("installed-revision\n")
    proc = harness.run(FC_PLAYBOOK_DIR=playbook.as_posix(), FC_PLAYBOOK_REF="other-revision", FC_PHASE="maintenance:reconcile-docs")
    assert proc.returncode == 1
    assert "installed playbook revision does not match" in proc.stderr
    assert not (harness.work / "repo").exists()
    assert not (harness.work / "mcp.json").exists()


def test_matching_playbook_revision_runs_with_the_local_bundle(harness):
    playbook = harness.tmp / "playbook"
    playbook.mkdir()
    (playbook / "REVISION").write_text("installed-revision\n")
    proc = harness.run(FC_PLAYBOOK_DIR=playbook.as_posix(), FC_PLAYBOOK_REF="installed-revision", FC_PHASE="maintenance:reconcile-docs")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert (harness.work / "repo").is_dir()


@pytest.mark.parametrize("phase", ["maintenance:reconcile-docs", "promotion:production"])
def test_worker_uses_approved_source_even_after_default_branch_moves(harness, phase):
    approved = harness._git("--git-dir", str(harness.origin), "rev-parse", "refs/heads/main").strip()
    seed = harness.tmp / "seed"
    (seed / "later.txt").write_text("not approved\n")
    harness._git("add", "later.txt", cwd=seed)
    harness._git("commit", "-q", "-m", "feat: later work", cwd=seed)
    harness._git("push", str(harness.origin), "main", cwd=seed)
    later = harness._git("--git-dir", str(harness.origin), "rev-parse", "refs/heads/main").strip()
    proc = harness.run(FC_SOURCE_REVISION=approved, FC_PHASE=phase)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    checkout = harness.work / "repo"
    assert harness._git("rev-parse", "HEAD", cwd=checkout).strip() == approved
    assert harness._git("branch", "--show-current", cwd=checkout).strip() == "main"
    assert not (checkout / "later.txt").exists()
    harness._git("commit", "-q", "--allow-empty", "-m", "fix: approved work", cwd=checkout)
    push = subprocess.run(["git", "push", "origin", "HEAD"], cwd=checkout, env=harness.env, capture_output=True, text=True, check=False)
    assert push.returncode != 0
    assert harness._git("--git-dir", str(harness.origin), "rev-parse", "refs/heads/main").strip() == later


@pytest.mark.parametrize("revision, message", [("", "FC_SOURCE_REVISION is required"), ("main", "full commit SHA"), ("f" * 40, "approved source revision is unavailable")])
def test_unavailable_or_unpinned_source_never_reaches_the_agent(harness, revision, message):
    proc = harness.run(FC_SOURCE_REVISION=revision, FC_PHASE="maintenance:reconcile-docs")
    assert proc.returncode == 1
    assert message in proc.stderr
    assert not (harness.work / "mcp.json").exists()


def test_managed_home_does_not_fall_back_when_its_source_pin_is_missing(harness):
    proc = harness.run(FC_SOURCE_REVISION="", FC_PHASE="maintenance:resolve", FC_HOME_BRANCH="main", FC_PAIR_REPO="partner/home")
    assert proc.returncode == 1
    assert "FC_SOURCE_REVISION is required" in proc.stderr
    assert not (harness.work / "repo").exists()


@pytest.mark.parametrize("pin_home", [True, False])
def test_managed_checkout_verifies_the_foreign_commit_space(harness, pin_home):
    foreign_seed = harness.tmp / "foreign-seed"
    foreign_origin = harness.tmp / "foreign.git"
    harness._git("init", "-q", str(foreign_seed))
    (foreign_seed / "home.txt").write_text("foreign approved code\n")
    harness._git("add", "home.txt", cwd=foreign_seed)
    harness._git("commit", "-q", "-m", "chore: foreign source", cwd=foreign_seed)
    home_sha = harness._git("rev-parse", "HEAD", cwd=foreign_seed).strip()
    harness._git("clone", "-q", "--bare", str(foreign_seed), str(foreign_origin))
    harness._git("config", "--global", f"url.file:///{foreign_origin.as_posix()}.insteadOf", "https://github.com/partner/home.git")
    install_sha = harness._git("--git-dir", str(harness.origin), "rev-parse", "refs/heads/main").strip()
    proc = harness.run(FC_PHASE="maintenance:reconcile-docs", FC_HOME_BRANCH="main", FC_PAIR_REPO="partner/home", FC_PAIR_TOKEN="foreign-token", FC_SOURCE_REVISION=home_sha if pin_home else install_sha)
    if pin_home:
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert harness._git("rev-parse", "HEAD", cwd=harness.work / "repo").strip() == home_sha
        assert (harness.work / "repo" / "home.txt").read_text() == "foreign approved code\n"
    else:
        assert proc.returncode == 1
        assert "approved source revision is unavailable" in proc.stderr
        assert not (harness.work / "mcp.json").exists()


@intent('INT-FC-R20')
@pytest.mark.parametrize('record', ['status: complete\nbody without frontmatter', '---\nstatus: complete\ninvalid: [unterminated\n---\n', '---\nother: value\n---\n\nstatus: complete\n'])
def test_body_only_or_malformed_yaml_never_completes_the_worker(harness, record):
    proc = _delivery(harness, FAKE_RECORD_CONTENT=record)
    assert proc.returncode == 1
    assert 'not complete' in proc.stderr
    assert 'signed: ' not in harness.scratch_file('handoff.md')
