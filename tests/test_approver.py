"""The worker's permission-prompt tool (devops/approver.py) behaves as #212 says.

test_entrypoint_execution.py runs it from the agent's MCP config inside the real script;
this file speaks MCP to it over stdio, as the agent's CLI does.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pytest_intent import intent

_APPROVER = Path(__file__).resolve().parents[1] / "devops" / "approver.py"


def _speak(answers: Path, *messages: object) -> list[dict]:
    lines = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages)
    proc = subprocess.run(
        [sys.executable, str(_APPROVER), str(answers)],
        input=lines, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines()]


@intent("INT-FC-R195")
def test_every_ask_is_allowed_with_its_own_input_and_recorded(tmp_path: Path) -> None:
    answers = tmp_path / "approvals.jsonl"
    ask = {"command": "git push origin HEAD", "description": "push the record"}
    replies = _speak(
        answers,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        "not json",
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "approve", "arguments": {"tool_name": "Bash", "input": ask, "tool_use_id": "toolu_a"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
    )
    assert [r["id"] for r in replies] == [1, 2, 3, 4]
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert [t["name"] for t in replies[1]["result"]["tools"]] == ["approve"]
    decision = json.loads(replies[2]["result"]["content"][0]["text"])
    assert decision == {"behavior": "allow", "updatedInput": ask}
    assert "error" in replies[3]
    recorded = [json.loads(line) for line in answers.read_text(encoding="utf-8").splitlines()]
    assert recorded == [{"behavior": "allow", "tool": "Bash", "input": ask}]
