"""Read observation times and explicit collection coverage."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.services.projections.observation_schedule import (
    FRESHNESS_WINDOW,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SnapshotMetadata:
    def __init__(
        self,
        observations: ObservationStore,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.observations = observations
        self.clock = clock

    def execute(self, repo: str = "", *, deliveries: bool = False) -> dict:
        """Freshness of ``repo``'s observation. A delivery read also carries the delivery
        index's hold: while its scan fails, the read is no newer than the index's last
        complete scan, and unavailable when none has completed (INT-FC-R144)."""
        metadata = self.observations.metadata.get(repo, {})
        freshness = dict(metadata.get("freshness") or {})
        if not freshness:
            report = metadata.get("coverage") or {}
            freshness = {
                "state": "stale" if report else "loading",
                "observed_at": None,
                "last_attempt_at": report.get("last_attempt_at"),
                "reason_code": "",
                "coverage": {
                    "complete": bool(report.get("complete")),
                    "observed": report.get("observed", 0),
                    "total": report.get("total"),
                },
            }
        if deliveries and self.observations.delivery_stale_since:
            scanned = self.observations.delivery_observed_at
            own = freshness.get("observed_at")
            if scanned and own:
                scanned = min(own, scanned, key=datetime.fromisoformat)
            freshness.update(
                state="stale" if scanned else "unavailable",
                observed_at=scanned,
                reason_code="source_unavailable",
                coverage={**freshness["coverage"], "complete": False},
            )
        observed = freshness.get("observed_at")
        if observed:
            age = (self.clock() - datetime.fromisoformat(observed)).total_seconds()
            freshness["age_seconds"] = max(0, age)
            if age > FRESHNESS_WINDOW.total_seconds() and freshness["state"] == "fresh":
                freshness["state"] = "stale"
                freshness["reason_code"] = "observation_expired"
        return {"freshness": freshness}
