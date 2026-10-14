"""The worker's run-figures writer (devops/record_run.py) behaves as #115 says.

It is the entrypoint's own deterministic writer of the `run` and `run_*` frontmatter
keys - the keys foundry-analytics reads for a phase's ledger. test_entrypoint_execution.py
runs it inside the real script; this file pins the helper's own contract as the CLI the
script invokes: the first write, the add-on-retry, and the cases that write nothing
without failing anything.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_intent import intent

_HELPER = Path(__file__).resolve().parents[1] / "devops" / "record_run.py"

_RECORD = """---
phase: build+ship
skill: run-delivery-plan
status: gate
gate: delivery
signed: pending
reviewed:
run:
attempt: 1
mode: one-shot
started: 2026-09-22T09:58:00Z
finished:
credential_ref: fc-run-app
---

# Build record

The prose says run_tokens: 999 and stays exactly as written.
"""

_MODEL = "claude-opus-4-1-20250805"
_SLUG = "claude_opus_4_1_20250805"
_NARRATION = (
    '{"type":"system","subtype":"init","session_id":"s1"}',
    '{"type":"assistant","message":{"content":[{"type":"text","text":"working"}]}}',
    "worker: a line that is not JSON at all",
)
_ARGS = (
    "--run", "delivery-app-x7k2p",
    "--agent", "builder",
    "--started", "2026-09-22T10:00:00Z",
    "--finished", "2026-09-22T10:12:34Z",
)


def _usage(inp: int, out: int, read: int, create: int, cost: float) -> dict[str, object]:
    return {
        "inputTokens": inp, "outputTokens": out, "cacheReadInputTokens": read,
        "cacheCreationInputTokens": create, "webSearchRequests": 0, "costUSD": cost,
        "contextWindow": 200000,
    }


def _event(
    *, inp: int = 1000, out: int = 50, read: int = 20000, create: int = 3000, cost: float = 0.4523,
    turns: int = 12, model_usage: dict[str, object] | None = None,
) -> str:
    event: dict[str, object] = {
        "type": "result", "subtype": "success", "is_error": False, "duration_ms": 754000,
        "num_turns": turns, "total_cost_usd": cost,
        "usage": {
            "input_tokens": inp, "output_tokens": out,
            "cache_read_input_tokens": read, "cache_creation_input_tokens": create,
        },
    }
    if model_usage is not None:
        event["modelUsage"] = model_usage
    return json.dumps(event)


def _stream(tmp_path: Path, *lines: str, name: str = "agent.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("".join(f"{ln}\n" for ln in lines), encoding="utf-8", newline="\n")
    return path


def _repo(tmp_path: Path, record: str = _RECORD) -> Path:
    scratch = tmp_path / ".delivery"
    scratch.mkdir(exist_ok=True)
    (scratch / "build.md").write_bytes(record.encode("utf-8"))
    return tmp_path


def _run(repo: Path, stream: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_HELPER), "--repo", str(repo), "--record", "build.md",
         "--stream", str(stream), *args],
        capture_output=True, text=True, encoding="utf-8",
    )


def _record(repo: Path) -> str:
    return (repo / ".delivery" / "build.md").read_bytes().decode("utf-8")


def _keys(text: str) -> dict[str, str]:
    block = text.split("---", 2)[1]
    return {k.strip(): v.strip() for k, _, v in (ln.partition(":") for ln in block.splitlines()) if k.strip()}


def _without_owned(text: str) -> str:
    return "".join(ln for ln in text.splitlines(keepends=True) if not re.match(r"^run(_\w+)?:", ln))


@intent("INT-FC-R161")
def test_a_first_write_records_every_key_and_leaves_every_other_byte_alone(tmp_path):
    repo = _repo(tmp_path)
    stream = _stream(tmp_path, *_NARRATION, _event(model_usage={_MODEL: _usage(1000, 50, 20000, 3000, 0.4523)}))
    proc = _run(repo, stream, *_ARGS, "--model", "claude-opus-4-1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = _record(repo)
    keys = _keys(text)
    assert keys["run"] == "delivery-app-x7k2p"
    assert keys["run_agent"] == "builder"
    assert keys["run_model"] == "claude-opus-4-1"
    assert keys["run_started"] == "2026-09-22T10:00:00Z"
    assert keys["run_finished"] == "2026-09-22T10:12:34Z"
    assert keys["run_seconds"] == "754"  # 10:00:00 to 10:12:34
    assert keys["run_tokens"] == "24050"  # every type summed
    assert keys["run_cost"] == "0.452300"
    assert keys["run_tokens_input"] == "1000"
    assert keys["run_tokens_output"] == "50"
    assert keys["run_tokens_cache_read"] == "20000"
    assert keys["run_tokens_cache_creation"] == "3000"
    assert keys["run_turns"] == "12"
    assert keys[f"run_model_{_SLUG}_tokens"] == "24050"
    assert keys[f"run_model_{_SLUG}_cost"] == "0.452300"
    # Every other byte: the record minus the owned lines is the original minus its `run:`.
    assert _without_owned(text) == _without_owned(_RECORD)
    # `run:` is rewritten on the line the record helper put it, not appended a second time.
    assert text.splitlines()[7] == "run: delivery-app-x7k2p"
    assert text.count("run:") == 1
    assert "Run figures recorded in .delivery/build.md: 24050 tokens, 0.452300 USD, 12 turns" in proc.stdout


@intent("INT-FC-R161")
def test_a_retry_adds_the_figures_and_keeps_the_attempts_span(tmp_path):
    repo = _repo(tmp_path)
    first = _stream(tmp_path, _event(model_usage={_MODEL: _usage(1000, 50, 20000, 3000, 0.4523)}), name="1.jsonl")
    second = _stream(
        tmp_path,
        _event(inp=200, out=10, read=4000, create=500, cost=0.1, turns=3, model_usage={
            _MODEL: _usage(100, 5, 2000, 250, 0.05),
            "claude-haiku-4-5": _usage(100, 5, 2000, 250, 0.05),
        }),
        name="2.jsonl",
    )
    assert _run(repo, first, *_ARGS, "--model", "m-one").returncode == 0
    proc = _run(
        repo, second, "--run", "delivery-app-x7k2p-retry", "--agent", "builder", "--model", "m-two",
        "--started", "2026-09-22T10:20:00Z", "--finished", "2026-09-22T10:31:00Z",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = _record(repo)
    keys = _keys(text)
    # The identity is the latest run's; the span is the attempt's whole.
    assert keys["run"] == "delivery-app-x7k2p-retry"
    assert keys["run_model"] == "m-two"
    assert keys["run_started"] == "2026-09-22T10:00:00Z"
    assert keys["run_finished"] == "2026-09-22T10:31:00Z"
    # The seconds add, so the gap between the attempts is never read as run time.
    assert keys["run_seconds"] == str(754 + 660)
    # The figures add: a retried attempt still cost what it cost.
    assert keys["run_tokens"] == str(24050 + 4710)
    assert keys["run_cost"] == "0.552300"
    assert keys["run_turns"] == "15"
    assert keys["run_tokens_input"] == "1200"
    assert keys[f"run_model_{_SLUG}_tokens"] == str(24050 + 2355)
    assert keys[f"run_model_{_SLUG}_cost"] == "0.502300"
    assert keys["run_model_claude_haiku_4_5_tokens"] == "2355"
    assert keys["run_model_claude_haiku_4_5_cost"] == "0.050000"
    # Rewritten in place: one line per key in the block, and the rest of the record as it was
    # (the body's own "run_tokens: 999" prose included).
    front = text.split("---", 2)[1]
    assert front.count("run_tokens:") == 1 and front.count("run_cost:") == 1
    assert _without_owned(text) == _without_owned(_RECORD)


@intent("INT-FC-R161")
def test_the_tokens_count_the_work_the_agent_delegated(tmp_path):
    """The result event's top-level usage covers the agent's own turns; its per-model usage
    also covers the subagents it delegated to, and is what the cost was charged for. A phase
    that delegated recorded a sixth of its tokens beside the whole of its cost."""
    repo = _repo(tmp_path)
    own_turns = _event(inp=10, out=3056, read=485249, create=5979, cost=1.415995, turns=4, model_usage={
        _MODEL: _usage(60, 20000, 2700000, 148506, 1.2),
        "claude-haiku-4-5": _usage(40, 1000, 90000, 9000, 0.215995),
    })
    assert _run(repo, _stream(tmp_path, own_turns), *_ARGS).returncode == 0
    keys = _keys(_record(repo))
    assert keys["run_tokens_input"] == "100"
    assert keys["run_tokens_output"] == "21000"
    assert keys["run_tokens_cache_read"] == "2790000"
    assert keys["run_tokens_cache_creation"] == "157506"
    assert keys["run_tokens"] == str(100 + 21000 + 2790000 + 157506)
    assert int(keys["run_tokens"]) == int(keys[f"run_model_{_SLUG}_tokens"]) + int(keys["run_model_claude_haiku_4_5_tokens"])
    assert keys["run_cost"] == "1.415995"


@intent("INT-FC-R193")
def test_the_record_counts_what_the_harness_denied_and_a_retry_adds_it(tmp_path):
    repo = _repo(tmp_path)
    denied = json.loads(_event(model_usage={_MODEL: _usage(1000, 50, 20000, 3000, 0.4523)}))
    denied["permission_denials"] = [{"tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "git push"}}] * 2
    assert _run(repo, _stream(tmp_path, json.dumps(denied), name="1.jsonl"), *_ARGS).returncode == 0
    assert _keys(_record(repo))["run_permission_denials"] == "2"
    denied["permission_denials"] = [denied["permission_denials"][0]]
    assert _run(repo, _stream(tmp_path, json.dumps(denied), name="2.jsonl"), *_ARGS).returncode == 0
    assert _keys(_record(repo))["run_permission_denials"] == "3"


@intent("INT-FC-R161")
def test_a_run_that_ended_before_its_record_exists_writes_nothing_and_says_so(tmp_path):
    (tmp_path / ".delivery").mkdir()
    proc = _run(tmp_path, _stream(tmp_path, _event()), *_ARGS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no .delivery/build.md" in proc.stdout and "not recorded" in proc.stdout
    assert not (tmp_path / ".delivery" / "build.md").exists()


@intent("INT-FC-R161")
@pytest.mark.parametrize(
    "lines",
    [
        (),
        _NARRATION,
        ("not json at all", "{broken", '["a","list"]'),
        ('{"type":"result_summary","usage":{"input_tokens":5}}',),
    ],
)
def test_a_stream_with_no_result_event_writes_nothing_and_does_not_fail(tmp_path, lines):
    repo = _repo(tmp_path)
    proc = _run(repo, _stream(tmp_path, *lines), *_ARGS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no result event" in proc.stdout and "not recorded" in proc.stdout
    assert _record(repo) == _RECORD


@intent("INT-FC-R161")
def test_a_stream_that_cannot_be_read_is_a_missing_result_event_not_a_failure(tmp_path):
    repo = _repo(tmp_path)
    proc = _run(repo, tmp_path / "never-written.jsonl", *_ARGS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no result event" in proc.stdout
    assert _record(repo) == _RECORD


@intent("INT-FC-R161")
def test_a_record_with_no_frontmatter_block_is_left_alone(tmp_path):
    bare = "# Build record\n\nA legacy record with no block.\n"
    repo = _repo(tmp_path, record=bare)
    proc = _run(repo, _stream(tmp_path, _event()), *_ARGS)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "no frontmatter block" in proc.stdout
    assert _record(repo) == bare


@intent("INT-FC-R161")
def test_run_model_is_the_launch_model_else_the_busiest_model_the_event_reports(tmp_path):
    usage = {
        "claude-haiku-4-5": _usage(100, 10, 0, 0, 0.01),
        _MODEL: _usage(1000, 50, 20000, 3000, 0.45),
    }
    # No launch model: the event's busiest model is the run's.
    repo = _repo(tmp_path)
    assert _run(repo, _stream(tmp_path, _event(model_usage=usage)), *_ARGS).returncode == 0
    assert _keys(_record(repo))["run_model"] == _MODEL
    # A launch model wins over what the event reports.
    repo = _repo(tmp_path)
    assert _run(repo, _stream(tmp_path, _event(model_usage=usage)), *_ARGS, "--model", "opus").returncode == 0
    assert _keys(_record(repo))["run_model"] == "opus"
    # Neither: no `run_model` key is invented.
    repo = _repo(tmp_path)
    assert _run(repo, _stream(tmp_path, _event()), *_ARGS).returncode == 0
    assert "run_model" not in _keys(_record(repo))


@intent("INT-FC-R161")
def test_only_what_the_event_carries_is_written(tmp_path):
    # A harness that reports no cost and no turns writes no `run_cost` and no `run_turns`:
    # a zero would read as "free", which is a claim the event did not make.
    repo = _repo(tmp_path)
    event = json.dumps({"type": "result", "usage": {"input_tokens": 10, "output_tokens": 5}})
    assert _run(repo, _stream(tmp_path, event), *_ARGS).returncode == 0
    keys = _keys(_record(repo))
    assert keys["run_tokens"] == "15" and keys["run_tokens_cache_read"] == "0"
    assert "run_cost" not in keys and "run_turns" not in keys


@intent("INT-FC-R161")
def test_a_tiny_cost_is_written_as_its_cost_never_as_free(tmp_path):
    repo = _repo(tmp_path)
    event = _event(cost=0.00003, model_usage={_MODEL: _usage(1, 1, 0, 0, 0.00003)})
    assert _run(repo, _stream(tmp_path, event), *_ARGS).returncode == 0
    keys = _keys(_record(repo))
    assert keys["run_cost"] == "0.000030"
    assert keys[f"run_model_{_SLUG}_cost"] == "0.000030"


@intent("INT-FC-R161")
def test_only_a_column_zero_key_is_owned_so_a_nested_run_line_is_left_alone(tmp_path):
    nested = _RECORD.replace(
        "credential_ref: fc-run-app\n",
        "credential_ref: fc-run-app\nprovenance:\n  run: nested-value\n  run_tokens: 7\n",
    )
    repo = _repo(tmp_path, record=nested)
    assert _run(repo, _stream(tmp_path, _event()), *_ARGS).returncode == 0
    text = _record(repo)
    # The indented lines are not this helper's: untouched, in place, under their own key.
    assert "\nprovenance:\n  run: nested-value\n  run_tokens: 7\n" in text
    # The column-0 `run:` is the one rewritten, and the totals are appended once.
    assert "\nrun: delivery-app-x7k2p\n" in text
    assert text.count("\nrun_tokens: 24050\n") == 1
    assert _without_owned(text) == _without_owned(nested)


@intent("INT-FC-R161")
def test_the_records_own_line_endings_are_kept(tmp_path):
    crlf = _RECORD.replace("\n", "\r\n")
    repo = _repo(tmp_path, record=crlf)
    assert _run(repo, _stream(tmp_path, _event()), *_ARGS).returncode == 0
    raw = (repo / ".delivery" / "build.md").read_bytes()
    assert raw.count(b"\n") == raw.count(b"\r\n")  # every line, the appended ones included
    assert b"run_tokens: 24050\r\n" in raw
    assert _without_owned(raw.decode("utf-8")) == _without_owned(crlf)


@intent("INT-FC-R161")
def test_a_malformed_stamp_is_refused_and_the_record_untouched(tmp_path):
    repo = _repo(tmp_path)
    proc = _run(repo, _stream(tmp_path, _event()), "--run", "r", "--started", "yesterday")
    assert proc.returncode == 1
    assert "REFUSED" in proc.stdout and "--started" in proc.stdout
    assert _record(repo) == _RECORD


@intent("INT-FC-R161")
def test_the_helper_is_stdlib_only_like_the_vendored_helpers_beside_it():
    """It runs on the worker image's bare python3, exactly as reach_gate.py and
    stamp_gate.py do; a dependency here is a dependency the image does not carry."""
    source = _HELPER.read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import)\s+([A-Za-z_]\w*)", source, re.MULTILINE))
    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported


@intent("INT-FC-R161")
def test_a_re_drive_the_next_day_adds_its_seconds_and_never_the_night_between(tmp_path):
    # demo-wheelee's build: attempt 1 ran 16 minutes one evening, attempt 2 ran 17 the next
    # morning. The span covers the night; the seconds are what the agent ran.
    repo = _repo(tmp_path)
    assert _run(
        repo, _stream(tmp_path, _event(), name="1.jsonl"), "--run", "r-1", "--agent", "builder",
        "--started", "2026-09-22T18:40:50Z", "--finished", "2026-09-22T18:56:58Z",
    ).returncode == 0
    assert _run(
        repo, _stream(tmp_path, _event(), name="2.jsonl"), "--run", "r-2", "--agent", "builder",
        "--started", "2026-09-23T09:07:10Z", "--finished", "2026-09-23T09:24:24Z",
    ).returncode == 0
    keys = _keys(_record(repo))
    assert keys["run_started"] == "2026-09-22T18:40:50Z" and keys["run_finished"] == "2026-09-23T09:24:24Z"
    assert keys["run_seconds"] == str(968 + 1034)


@intent("INT-FC-R161")
def test_a_record_written_before_the_key_starts_its_seconds_from_the_carried_span(tmp_path):
    carried = _RECORD.replace(
        "credential_ref: fc-run-app\n",
        "credential_ref: fc-run-app\nrun_started: 2026-09-21T08:00:00Z\nrun_finished: 2026-09-21T08:30:00Z\n",
    )
    repo = _repo(tmp_path, carried)
    assert _run(repo, _stream(tmp_path, _event()), *_ARGS).returncode == 0
    keys = _keys(_record(repo))
    # The earlier attempt left only its span (30 minutes): the sum starts there, never
    # from nothing, so the figure is never worse than the span a reader measured before.
    assert keys["run_seconds"] == str(1800 + 754)
    assert keys["run_started"] == "2026-09-21T08:00:00Z"


@intent("INT-FC-R161")
def test_a_clock_that_stepped_backwards_records_no_time_rather_than_a_zero(tmp_path):
    repo = _repo(tmp_path)
    assert _run(
        repo, _stream(tmp_path, _event()), "--run", "r", "--agent", "builder",
        "--started", "2026-09-22T10:05:00Z", "--finished", "2026-09-22T10:00:00Z",
    ).returncode == 0
    assert "run_seconds" not in _keys(_record(repo))
