"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


def helper_track_oneshot(
    handle: str,
    repo: str,
    ticket: int | None,
    result: str = "",
    *,
    observations: ObservationStore,
) -> None:
    """Track one one-shot drive: ONE row per ticket (INT-FC-R119). A ticket has a single
    drive in flight, so a new run for it retires the row it supersedes - the re-drive's
    previous attempt, a second press over a settled receipt, a run re-derived after a
    restart. One row is what lets the ticket's own line read its drive unambiguously."""
    for h, e in list(observations.oneshot.items()):
        if (e["repo"], e["ticket"]) == (repo, ticket):
            del observations.oneshot[h]
    observations.oneshot[handle] = {
        "repo": repo,
        "ticket": ticket,
        "acted": False,
        "result": result,
        "ticks": 0,
        "settled": 0,
    }
