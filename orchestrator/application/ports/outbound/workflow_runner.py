"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata

__all__ = ["WorkflowRunner"]


class WorkflowRunner(Protocol):
    def metadata_of(self, handle: str) -> WorkflowMetadata:
        """Read authoritative workflow ownership and concurrency metadata."""
        ...

    def submit(
        self, workflow: CompiledWorkflow, *, delegated_grant_id: str | None = None
    ) -> str:
        """Submit opaque compiled execution input to the executor. Returns a run handle."""
        ...

    def status(self, handle: str) -> str:
        """The executor's phase for a submitted workflow (Running/Suspended/Failed/Succeeded)."""
        ...

    def list_runs(self) -> list[RunInventoryEntry]:
        """Every run the executor is tracking (Argo Workflows the Console labelled), newest
        first: handle, run id, mode, overall phase, who stopped it (`stop`), and timestamps.
        [] off-cluster. The phase is the Console's derivation, not raw Argo: a gate-parked run
        reads Suspended, and a run the Console stopped reads Stopping/Stopped rather than the
        Failed a shutdown produces."""
        ...

    def graph(self, handle: str) -> ExecutionGraph:
        """One run's node graph: the overall phase (derived as in list_runs), who stopped it,
        and each node (worker step, step group, gate suspend) with its own phase, message, and
        children - the live workflow DAG."""
        ...

    def stop(
        self,
        handle: str,
        terminate: bool = False,
        reason: str = "operator",
        *,
        expected_version: str | None = None,
    ) -> str:
        """Stop a run (patch spec.shutdown): Stop drains gracefully, Terminate kills now.
        `reason` records WHO stopped it (workflow.STOP_REASONS) on the run itself, so the
        Failed a shutdown produces can be reported as the deliberate close it was."""
        ...

    def resume(self, handle: str, *, expected_version: str | None = None) -> str:
        """Resume a suspended run (release its gate suspends). Returns a short status word."""
        ...

    def logs(self, handle: str, tail: int = 400, node_id: str | None = None) -> str:
        """The run's step logs (pod-prefixed tail), read live from the executor.
        node_id scopes the read to that node's pod. SourceUnavailable means the
        capture was not confirmed, including partial container reads. A confirmed
        empty inventory or successful empty outputs return an empty string."""
        ...

    def delete(self, handle: str, *, expected_version: str, expected_uid: str) -> str:
        """Delete only the observed workflow incarnation."""
        ...
