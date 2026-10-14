"""Name the repository a run belongs to."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner


class RunRepository:
    def __init__(
        self, *, observations: ObservationStore, workflows: WorkflowRunner | None
    ) -> None:
        self.observations = observations
        self.workflows = workflows

    def execute(self, handle: str) -> str | None:
        """The repository of an observed run, live or retained; a run submitted since the
        last observation is read from the executor. None for a run neither knows."""
        for run in self.observations.runs:
            if run.handle == handle:
                return run.repository
        if self.workflows is None or not handle:
            return None
        try:
            return self.workflows.metadata_of(handle).repository or None
        except Exception:  # noqa: BLE001 - an unknown run names no repository
            return None
