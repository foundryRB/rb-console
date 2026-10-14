"""A repository-scoped view over pending reconciliation observations."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


class ScopedObservationStore:
    def __init__(self, source: ObservationStore, repo: str) -> None:
        self.runs = [run for run in source.runs if run.repository == repo]
        self.graphs = source.graphs
        self.positions = source.positions
        self.terminal_seen = source.terminal_seen
        self.fleet = [row for row in source.fleet if row.repo == repo]
        self.fleet_stale_since = source.fleet_stale_since
        self.fleet_stale_reason = source.fleet_stale_reason
        self.delivery_stale_since = source.delivery_stale_since
        self.delivery_stale_reason = source.delivery_stale_reason
        self.delivery_observed_at = source.delivery_observed_at
        self.inbox = source.inbox
        self.inbox_tick = source.inbox_tick
        self.oneshot = {
            key: value
            for key, value in source.oneshot.items()
            if value.get("repo") == repo
        }
        self.refresh_lock = source.refresh_lock
        self.metadata = source.metadata
