"""Decode the semantic execution archive format at the persistence boundary."""

from dataclasses import MISSING, fields

from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.execution_node import ExecutionNode
from orchestrator.domain.model.retained_execution import RetainedExecution
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def _record(value: object, target: type) -> dict:
    """One record of ``target``'s fields as written. A field the record predates reads as
    its default, in the archive's own shape (a tuple default as a list), so a record written
    before a defaulted field existed stays readable; an unknown key, or a missing field with
    no default, is malformed."""
    if not isinstance(value, dict):
        raise TypeError("Execution archive record is malformed")
    known = {field.name: field for field in fields(target)}
    required = {
        name
        for name, field in known.items()
        if field.default is MISSING and field.default_factory is MISSING
    }
    if not set(value) <= set(known) or not required <= set(value):
        raise TypeError("Execution archive record is malformed")
    record = dict(value)
    for name, field in known.items():
        if name not in record:
            default = (
                field.default if field.default is not MISSING else field.default_factory()
            )
            record[name] = list(default) if isinstance(default, tuple) else default
    return record


def decode_execution(value: object) -> RetainedExecution:
    envelope = _record(value, RetainedExecution)
    run = _record(envelope["run"], RunInventoryEntry)
    if not all(isinstance(run[key], str) for key in ("handle", "name", "phase")):
        raise TypeError("Execution archive identity is malformed")
    if not isinstance(run["agents"], list) or any(
        not isinstance(agent, str) for agent in run["agents"]
    ):
        raise TypeError("Execution archive agents are malformed")
    for key, value_run in run.items():
        if (
            key not in {"agents", "ticket"}
            and value_run is not None
            and not isinstance(value_run, str)
        ):
            raise TypeError("Execution archive run fact is malformed")
    if run["ticket"] is not None and type(run["ticket"]) is not int:
        raise TypeError("Execution archive ticket is malformed")
    if run["kind"] not in {None, "delivery", "maintenance", "promotion"}:
        raise TypeError("Execution archive ownership kind is malformed")
    run["agents"] = tuple(run["agents"])
    graph = _record(envelope["graph"], ExecutionGraph)
    if not isinstance(graph["nodes"], list) or not isinstance(graph["phase"], str):
        raise TypeError("Execution archive graph is malformed")
    for key in ("name", "stop_reason", "progress"):
        if graph[key] is not None and not isinstance(graph[key], str):
            raise TypeError("Execution archive graph fact is malformed")
    nodes = []
    for item in graph["nodes"]:
        node = _record(item, ExecutionNode)
        if node["kind"] not in {"worker", "gate", "group", "unknown"}:
            raise TypeError("Execution archive node kind is malformed")
        if node["exit_code"] is not None and type(node["exit_code"]) is not int:
            raise TypeError("Execution archive exit code is malformed")
        for key, value_node in node.items():
            if (
                key not in {"children", "artifacts", "exit_code"}
                and value_node is not None
                and not isinstance(value_node, str)
            ):
                raise TypeError("Execution archive node fact is malformed")
        if not isinstance(node["node_id"], str) or not isinstance(node["name"], str):
            raise TypeError("Execution archive node identity is malformed")
        for key in ("children", "artifacts"):
            if not isinstance(node[key], list) or any(
                not isinstance(entry, str) for entry in node[key]
            ):
                raise TypeError("Execution archive node references are malformed")
            node[key] = tuple(node[key])
        nodes.append(ExecutionNode(**node))
    graph["nodes"] = tuple(nodes)
    return RetainedExecution(RunInventoryEntry(**run), ExecutionGraph(**graph))
