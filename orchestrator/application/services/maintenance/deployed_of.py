"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.domain.services.fleet.app_identity import deployment_health


def helper_deployed_of(
    repo: str, *, observations: ObservationStore
) -> tuple[str, bool | None]:
    """The repo's live signal from the warm fleet cache (the platform reads the
    fleet already does). What the platform offers is a STATUS WORD - running,
    paused, or a named unhealthy state - not a revision, and it rides as exactly
    that; deployment_health folds it to True (a running app), False (an EXPLICIT
    unhealthy word the platform names) or None (a paused app, an absent signal, or
    an unrecognised word). So a genuinely broken deployment surfaces as unhealthy
    while a paused app and an unreachable cluster are never guessed into it - the
    fleet inbox's 'drift' signal can now fire on a real report instead of never
    (INT-FC-R68)."""
    name = repo.split("/")[-1]
    for it in observations.fleet:
        if it.name == name:
            live = getattr(it, "live", "") or ""
            return (live, deployment_health(live))
    return ("", None)
