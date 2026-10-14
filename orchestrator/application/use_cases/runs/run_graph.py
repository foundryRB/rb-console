"""Read observed run graph without executor traffic."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.domain.model.execution_graph import ExecutionGraph


class RunGraph:
    def __init__(self, *, observations: ObservationStore) -> None:
        self.observations = observations

    def execute(self, handle: str) -> ExecutionGraph:
        return self.observations.graphs.get(handle, ExecutionGraph("unknown"))
