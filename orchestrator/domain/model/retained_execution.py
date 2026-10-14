from dataclasses import dataclass

from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


@dataclass(frozen=True)
class RetainedExecution:
    run: RunInventoryEntry
    graph: ExecutionGraph
