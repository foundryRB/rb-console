"""Projections shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner


def helper_activity_by_repo(
    *, workflows: WorkflowRunner | None
) -> tuple[dict[str, str], bool]:
    """Repository activity from delivery-kind executor observations, with source availability.

    Running and suspended signals use the captured full repository identity. An unavailable
    executor leaves activity unknown; a reachable executor with no live delivery run is idle.
    """
    if workflows is None:
        return ({}, False)
    try:
        rows = workflows.list_runs()
    except Exception:  # noqa: BLE001 - independent observations retain prior results
        return ({}, False)
    rank = {"running": 3, "suspended": 2, "idle": 1}
    by: dict[str, str] = {}
    for r in rows:
        repo = r.repository
        if r.kind != "delivery" or not isinstance(repo, str) or not repo:
            continue
        phase = str(r.phase)
        act = (
            "running"
            if phase in ("Running", "Pending")
            else "suspended"
            if phase == "Suspended"
            else "idle"
        )
        if rank[act] > rank.get(by.get(repo, ""), 0):
            by[repo] = act
    return (by, True)
