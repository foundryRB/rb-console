"""Archive evidence before deleting runs with authoritative ownership and CAS."""

from __future__ import annotations

import logging

from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.runs.line_runs import helper_line_runs
from orchestrator.application.services.runs.supersede_runs import helper_supersede_runs
from orchestrator.domain.delivery import same_repository
from orchestrator.domain.model.retained_execution import RetainedExecution


def helper_end_runs(
    repo: str,
    *,
    run_log_store: RunLogStore | None,
    workflows: WorkflowRunner | None,
    cap_run_retention: RunRetentionPort,
) -> None:
    if workflows is None:
        return
    try:
        helper_supersede_runs(repo, workflows=workflows)
        for row in helper_line_runs(repo, workflows=workflows):
            handle = str(row.handle)
            metadata = workflows.metadata_of(handle)
            if not same_repository(metadata.repository, repo) or metadata.kind != "delivery":
                continue
            if run_log_store is None:
                raise RuntimeError("Run evidence archive is required before cleanup")
            name = str(row.name)
            run_log_store.save_metadata(
                name, RetainedExecution(row, workflows.graph(handle))
            )
            if not run_log_store.has(name):
                run_log_store.save(
                    name,
                    workflows.logs(handle),
                    prune_after_seconds=cap_run_retention.execute()["ttl_failure_days"]
                    * 86400,
                )
            workflows.delete(
                handle,
                expected_version=metadata.resource_version,
                expected_uid=metadata.uid,
            )
    except Exception:
        logging.getLogger(__name__).exception("Run cleanup failed for %s", repo)
        raise
