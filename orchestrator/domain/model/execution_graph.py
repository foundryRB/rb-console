from dataclasses import dataclass

from orchestrator.domain.model.execution_node import ExecutionNode


@dataclass(frozen=True)
class ExecutionGraph:
    phase: str
    name: str | None = None
    stop_reason: str | None = None
    progress: str | None = None
    nodes: tuple[ExecutionNode, ...] = ()
