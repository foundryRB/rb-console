"""Collect due repository metadata and publish honest per-resource coverage."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from datetime import UTC, datetime

from orchestrator.application.ports.inbound.projections.maintenance_state import (
    MaintenanceStatePort,
)
from orchestrator.application.ports.inbound.promotion.promotion_options import (
    PromotionOptionsPort,
)
from orchestrator.application.ports.inbound.promotion.promotion_state import (
    PromotionStatePort,
)
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.services.projections.observation_schedule import (
    COLLECTION_DUE,
    FRESHNESS_WINDOW,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RefreshMetadata:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        maintenance: MaintenanceStatePort,
        promotion: PromotionStatePort,
        options: PromotionOptionsPort,
        config: DeliveryConfigPort,
        batch_size: int = 24,
        workers: int = 4,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.observations = observations
        self.maintenance = maintenance
        self.promotion = promotion
        self.options = options
        self.config = config
        self.batch_size = batch_size
        self.workers = workers
        self.clock = clock

    def execute(self, *, sweep: bool = False) -> dict:
        """Collect the repositories whose last attempt is due, oldest first, a few at a time
        and at most one batch per tick, publishing each repository as its reads complete.
        An explicit sweep collects every repository."""
        repos = sorted({row.repo for row in self.observations.fleet})
        started = self.clock()
        now = started.isoformat()
        due = sorted(
            (repo for repo in repos if sweep or self._due(repo, started)),
            key=lambda repo: self._freshness(repo).get("last_attempt_at") or "",
        )
        batch = due if sweep else due[: self.batch_size]
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(copy_context().run, self._collect, repo) for repo in batch]
            for future in as_completed(futures):
                repo, values, errors = future.result()
                self._publish(repo, values, errors, now)
                if errors:
                    failed.append(repo)
        finished = self.clock()
        observed = sum(bool(self._freshness(repo).get("observed_at")) for repo in repos)
        fresh = sum(self._fresh(repo, finished) for repo in repos)
        report = {
            "complete": fresh == len(repos) and not failed,
            "observed": observed,
            "fresh": fresh,
            "total": len(repos),
            "failed": failed,
            "last_attempt_at": now,
        }
        self.observations.metadata.setdefault("", {})["coverage"] = report
        return report

    def _collect(self, repo: str) -> tuple[str, dict, list[str]]:
        values: dict = {}
        errors: list[str] = []
        for key, capability in (
            ("maintenance_state", self.maintenance),
            ("promotion_state", self.promotion),
            ("promotion_options", self.options),
            ("delivery_config", self.config),
        ):
            try:
                values[key] = capability.execute(repo)
            except Exception:
                errors.append(key)
                logging.getLogger(__name__).warning(
                    "Observation failed: %s %s", repo, key, exc_info=True
                )
        return repo, values, errors

    def _publish(self, repo: str, values: dict, errors: list[str], now: str) -> None:
        current = {**self.observations.metadata.get(repo, {}), **values}
        prior = current.get("freshness") or {}
        current["freshness"] = {
            "state": "stale"
            if errors and prior.get("observed_at")
            else "unavailable"
            if errors
            else "fresh",
            "observed_at": prior.get("observed_at") if errors else now,
            "last_attempt_at": now,
            "reason_code": "source_unavailable" if errors else "",
            "coverage": {
                "complete": not errors,
                "observed": 4 - len(errors),
                "total": 4,
            },
        }
        self.observations.metadata[repo] = current

    def _freshness(self, repo: str) -> dict:
        return self.observations.metadata.get(repo, {}).get("freshness") or {}

    def _due(self, repo: str, at: datetime) -> bool:
        try:
            attempted = datetime.fromisoformat(self._freshness(repo)["last_attempt_at"])
        except (KeyError, TypeError, ValueError):
            return True
        return at - attempted >= COLLECTION_DUE

    def _fresh(self, repo: str, at: datetime) -> bool:
        freshness = self._freshness(repo)
        try:
            observed = datetime.fromisoformat(freshness["observed_at"])
        except (KeyError, TypeError, ValueError):
            return False
        return freshness.get("state") == "fresh" and at - observed <= FRESHNESS_WINDOW
