"""Release only a workflow belonging to the signed repository and scratch ref."""

from __future__ import annotations

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.runs.line_runs import helper_line_runs
from orchestrator.domain.delivery import same_repository
from orchestrator.domain.services.run_policy import STOP_SUPERSEDED


def helper_release_parked_run(
    repo: str, gate: str, *, workflows: WorkflowRunner | None, scratch_ref: str
) -> None:
    if workflows is None:
        return
    released = False
    for row in helper_line_runs(repo, workflows=workflows):
        if row.phase != "Suspended":
            continue
        handle = str(row.handle)
        metadata = workflows.metadata_of(handle)
        if not same_repository(metadata.repository, repo) or metadata.scratch_ref != scratch_ref:
            continue
        if not released and row.parked_gate == gate:
            workflows.resume(handle, expected_version=metadata.resource_version)
            released = True
        else:
            workflows.stop(
                handle,
                reason=STOP_SUPERSEDED,
                expected_version=metadata.resource_version,
            )
