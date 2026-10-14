"""Explicit semantic execution builders for outbound-port test doubles."""

from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.execution_node import ExecutionNode
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def run_row(value):
    if isinstance(value, RunInventoryEntry):
        return value
    aliases = {
        "repo": "repository",
        "revision": "resource_version",
        "maintenance": "maintenance_act",
        "promotion": "promotion_target",
        "repo_slug": "repository_slug",
        "stop": "stop_reason",
        "created": "created_at",
        "started": "started_at",
        "finished": "finished_at",
    }
    fields = {
        aliases.get(key, key): item for key, item in value.items() if key != "grant"
    }
    fields.setdefault("handle", "")
    fields.setdefault("name", "")
    fields.setdefault("phase", "unknown")
    fields["agents"] = tuple(fields.get("agents") or ())
    if fields.get("ticket") is not None:
        fields["ticket"] = int(fields["ticket"])
    fields["grant_id"] = (value.get("grant") or {}).get("grant_id")
    return RunInventoryEntry(**fields)


def run_rows(values):
    return [run_row(value) for value in values]


def execution_graph(value):
    if isinstance(value, ExecutionGraph):
        return value
    nodes = []
    for value_node in value.get("nodes", []):
        aliases = {
            "id": "node_id",
            "type": "kind",
            "exitCode": "exit_code",
            "startedAt": "started_at",
            "finishedAt": "finished_at",
        }
        fields = {aliases.get(key, key): item for key, item in value_node.items()}
        fields.setdefault("node_id", "test-node")
        fields.setdefault("name", fields["node_id"])
        fields["kind"] = {"Pod": "worker", "Suspend": "gate", "StepGroup": "group"}.get(
            fields.get("kind"), "unknown"
        )
        fields["children"] = tuple(fields.get("children") or ())
        fields["artifacts"] = tuple(fields.get("artifacts") or ())
        if fields.get("exit_code") is not None:
            fields["exit_code"] = int(fields["exit_code"])
        nodes.append(ExecutionNode(**fields))
    return ExecutionGraph(
        value.get("phase", "unknown"),
        value.get("name"),
        value.get("stop"),
        value.get("progress"),
        tuple(nodes),
    )
