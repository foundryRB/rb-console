"""Answer a worker run's permission asks: the agent's ``--permission-prompt-tool``
(foundry-console#212).

Some model keys carry an organisation policy that turns bypass mode off, and a headless
session in any other mode refuses every ask with nobody to answer it. The policy overrides
``--allowedTools``, an allow hook and the harness's own auto mode, but the prompt tool
receives every ask and its answer is honoured (playbook#482). The organisation's deny rules
refuse before an ask exists, so they never reach this tool.

A stdio MCP server, standard library only, with one tool, ``approve``. It allows every ask
with the ask's own input and appends the answer, one JSON line, to the file named as its
argument, outside the clone; the worker prints those lines after the turn. On a key where
bypass holds, the harness never asks and the tool is never called.

    python3 approver.py <answers-file>
"""
from __future__ import annotations

import json
import sys

_TOOL = {
    "name": "approve",
    "description": "Answer a permission ask: allow it, with its input unchanged.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "tool_name": {"type": "string"},
            "input": {"type": "object"},
            "tool_use_id": {"type": "string"},
        },
        "required": ["tool_name", "input"],
    },
}


def answer(message: dict, answers: str) -> dict | None:
    """The response to one JSON-RPC message, or None for a notification."""
    if "id" not in message:
        return None
    method, params = message.get("method"), message.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "approver", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {"tools": [_TOOL]}
    elif method == "tools/call" and params.get("name") == "approve":
        ask = params.get("arguments") or {}
        with open(answers, "a", encoding="utf-8") as out:
            out.write(json.dumps({"behavior": "allow", "tool": ask.get("tool_name"), "input": ask.get("input")}) + "\n")
        decision = {"behavior": "allow", "updatedInput": ask.get("input") or {}}
        result = {"content": [{"type": "text", "text": json.dumps(decision)}]}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def main() -> int:
    answers = sys.argv[1]
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except ValueError:
            continue
        response = answer(message, answers) if isinstance(message, dict) else None
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
