"""Presentation facts derived from a phase record and an observed run graph."""

import re

from orchestrator.domain.model.execution_graph import ExecutionGraph


def phase_presentation(
    phase: dict, graph: ExecutionGraph | None, learned_on: str | None
) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", phase["name"].lower()).strip("-")
    nodes = [
        node
        for node in (graph.nodes if graph else ())
        if node.kind == "worker" and node.template == "worker-" + slug
    ]
    newest = max(nodes, key=lambda node: node.started_at or "", default=None)
    live = newest.phase if newest else None
    stopped = bool(graph and graph.stop_reason) or bool(
        newest and newest.exit_code == 143
    )
    if live in {"Running", "Pending"}:
        return {"tone": "running", "sub_label": "running"}
    if live in {"Failed", "Error"}:
        if stopped:
            return {"tone": "warn", "sub_label": "stopped by operator"}
        return {
            "tone": "failed",
            "sub_label": "failed" + (f" ×{len(nodes)}" if len(nodes) > 1 else ""),
        }
    if phase["needs_review"]:
        return {"tone": "warn", "sub_label": "needs review"}
    if phase["record_present"] or learned_on:
        signed = phase["gate_signed_on"]
        suffix = (
            f" · signed {signed}"
            if signed
            else f" · learned {learned_on}"
            if learned_on
            else ""
        )
        return {"tone": "done", "sub_label": "done" + suffix}
    if phase["is_current"]:
        return {"tone": "current", "sub_label": "current"}
    return {"tone": "locked", "sub_label": "queued"}
