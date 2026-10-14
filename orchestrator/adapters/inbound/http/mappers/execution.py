"""Map semantic execution facts to the public console contract."""

from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def run_dto(run: RunInventoryEntry) -> dict:
    return {
        "handle": run.handle,
        "name": run.name,
        "run_id": run.run_id,
        "repo": run.repository,
        "revision": run.resource_version,
        "mode": run.mode,
        "kind": run.kind,
        "promotion": run.promotion_target,
        "maintenance": run.maintenance_act,
        "ticket": str(run.ticket) if run.ticket is not None else None,
        "repo_slug": run.repository_slug,
        "phase": run.phase,
        "stop": run.stop_reason,
        "created": run.created_at,
        "started": run.started_at,
        "finished": run.finished_at,
        "progress": run.progress,
        "agents": list(run.agents),
    }


def graph_dto(graph: ExecutionGraph) -> dict:
    return {
        **({"name": graph.name} if graph.name is not None else {}),
        "phase": graph.phase,
        "stop": graph.stop_reason,
        "progress": graph.progress,
        "nodes": [
            {
                "id": node.node_id,
                "name": node.name,
                "type": {"worker": "Pod", "gate": "Suspend", "group": "StepGroup"}.get(
                    node.kind
                ),
                "phase": node.phase,
                "template": node.template,
                "agent": node.agent,
                "message": node.message,
                "exitCode": str(node.exit_code) if node.exit_code is not None else None,
                "children": list(node.children),
                "startedAt": node.started_at,
                "finishedAt": node.finished_at,
                "artifacts": list(node.artifacts),
                "refusal": node.refusal,
            }
            for node in graph.nodes
        ],
    }
