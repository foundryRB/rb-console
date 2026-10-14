"""Stop active runs belonging to the authoritative delivery repository."""

from __future__ import annotations

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.runs.line_runs import helper_line_runs
from orchestrator.domain.delivery import same_repository
from orchestrator.domain.services.run_policy import STOP_SUPERSEDED


def helper_supersede_runs(repo: str, *, workflows: WorkflowRunner | None) -> None:
    if workflows is None:
        return
    for row in helper_line_runs(repo, workflows=workflows):
        if row.phase in ("Running", "Suspended", "Pending"):
            handle = str(row.handle)
            metadata = workflows.metadata_of(handle)
            if same_repository(metadata.repository, repo):
                workflows.stop(
                    handle,
                    reason=STOP_SUPERSEDED,
                    expected_version=metadata.resource_version,
                )
