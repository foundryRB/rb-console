"""Read workflow rows with truthful source failure semantics."""

from __future__ import annotations

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def helper_list_run_rows(
    *, workflows: WorkflowRunner | None
) -> list[RunInventoryEntry]:
    return workflows.list_runs() if workflows is not None else []
