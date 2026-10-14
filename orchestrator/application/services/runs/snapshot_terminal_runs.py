"""Runs shared orchestration over explicit contracts."""

from __future__ import annotations

import logging

from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.definitions import (
    _SNAPSHOT_TAIL_LINES,
    _TERMINAL_RUN_PHASES,
)
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def helper_snapshot_terminal_runs(
    rows: list[RunInventoryEntry],
    *,
    run_log_store: RunLogStore | None,
    workflows: WorkflowRunner | None,
    cap_run_retention: RunRetentionPort,
) -> None:
    """The background collector retains each terminal run's confirmed log tail.

    A successful empty capture is retained. A source failure leaves capture pending
    for the next observation; published metadata reads use the prepared snapshot.
    The archive retention follows the configured failed-workflow horizon (INT-FC-R108).
    """
    if run_log_store is None or workflows is None:
        return
    prune_seconds: int | None = None
    for r in rows:
        name = str(r.name or "")
        if not name or r.phase not in _TERMINAL_RUN_PHASES:
            continue
        try:
            if run_log_store.has(name):
                continue
            if prune_seconds is None:
                prune_seconds = cap_run_retention.execute()["ttl_failure_days"] * 86400
            run_log_store.save(
                name,
                workflows.logs(str(r.handle or ""), _SNAPSHOT_TAIL_LINES),
                prune_after_seconds=prune_seconds,
            )
        except Exception:
            logging.getLogger(__name__).warning(
                "Independent observation failed", exc_info=True
            )
            continue
