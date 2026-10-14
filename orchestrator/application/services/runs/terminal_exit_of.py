"""Runs shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.runs.run_graph import RunGraphPort


def helper_terminal_exit_of(handle: str, *, cap_run_graph: RunGraphPort) -> str:
    """The exit code the run's failed worker returned, read off the node graph; "" when no
    node carries one. The LAST failed pod node wins: a retried phase leaves an attempt per
    try and the final one is the code Argo stopped on."""
    code = ""
    for node in cap_run_graph.execute(handle).nodes:
        if (
            node.kind == "worker"
            and node.phase in ("Failed", "Error")
            and node.exit_code is not None
        ):
            code = str(node.exit_code)
    return code
