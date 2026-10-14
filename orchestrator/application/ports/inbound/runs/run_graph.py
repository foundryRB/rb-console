"""RunGraph application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.execution_graph import ExecutionGraph


@runtime_checkable
class RunGraphPort(Protocol):
    def execute(self, handle: str) -> ExecutionGraph: ...
