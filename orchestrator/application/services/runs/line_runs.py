"""Select runs by authoritative repository and execution kind."""

from __future__ import annotations

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.domain.delivery import same_repository
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry

#: Argo's own terminal phases plus the console's Stopped (INT-FC-R124).
_FINISHED = frozenset({"Succeeded", "Failed", "Error", "Stopped"})


def helper_line_runs(
    repo: str, *, workflows: WorkflowRunner | None
) -> list[RunInventoryEntry]:
    if workflows is None:
        return []
    rows = workflows.list_runs()
    selected = []
    for row in rows:
        handle = str(row.handle or "")
        if not handle:
            continue
        try:
            metadata = workflows.metadata_of(handle)
        except Conflict:
            # An execution the console cannot classify: one an earlier console created
            # without the captured coordinates. Finished, it decides nothing for the line
            # (a close cannot attribute it either; retention ages it out) and must not
            # refuse every command until then; live, the scan would stop or resume it, so
            # the fail-closed read stands (INT-FC-R175).
            if row.phase in _FINISHED:
                continue
            raise
        if same_repository(metadata.repository, repo) and metadata.kind == "delivery":
            selected.append(row)
    return selected
