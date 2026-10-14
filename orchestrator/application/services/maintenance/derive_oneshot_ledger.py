"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

import logging
from functools import partial

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.identity.norm_slug import helper_norm_slug
from orchestrator.application.services.maintenance.track_oneshot import (
    helper_track_oneshot,
)
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


def helper_derive_oneshot_ledger(
    runs: list[RunInventoryEntry] | None = None,
    *,
    observations: ObservationStore,
    workflows: WorkflowRunner | None,
) -> None:
    """Rebuild the judge's pending set from the executor (derived state, like
    everything else here): each one-shot resolve run carries its ticket and repo
    slug as labels, so a pod restart cannot orphan a drive - the next tick
    re-derives it. Only the NEWEST run per ticket is tracked: a retry (INT-FC-R75)
    adds a fresh run for the same ticket, and the judge acts on the latest one, never
    each superseded attempt.

    A ticket's LIVE row is authoritative over the executor's list, which lags a fresh
    submit by a tick; a SETTLED one is a receipt the newest run supersedes, so a ticket
    driven again after its PR parked is judged rather than swallowed by the old outcome."""
    if runs is None:
        if workflows is None:
            return
        try:
            runs = workflows.list_runs()
        except Exception:
            logging.getLogger(__name__).warning(
                "Observation source unavailable", exc_info=True
            )
            return
    {partial(helper_norm_slug)(it.name): it.repo for it in observations.fleet}
    live = {
        (e["repo"], e["ticket"])
        for e in observations.oneshot.values()
        if not e["acted"]
    }
    seen: set[tuple[str, int]] = set()
    for r in runs:
        if (
            r.kind != "maintenance"
            or r.maintenance_act != "resolve"
            or r.mode != "one-shot"
        ):
            continue
        handle = r.handle or ""
        repo = str(r.repository or "")
        if not repo or "/" not in repo:
            continue
        try:
            ticket = int(r.ticket or 0)
        except (TypeError, ValueError):
            ticket = 0
        if not handle or not repo or (not ticket):
            continue
        key = (repo, ticket)
        if key in seen:
            continue
        seen.add(key)
        if handle in observations.oneshot or key in live:
            continue
        partial(helper_track_oneshot, observations=observations)(handle, repo, ticket)
