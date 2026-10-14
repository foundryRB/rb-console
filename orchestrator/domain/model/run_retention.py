"""How long completed execution evidence remains available."""

from dataclasses import dataclass

from orchestrator.domain.services.run_policy import (
    POD_GC_DELAY_HOURS_DEFAULT,
    TTL_FAILURE_DAYS_DEFAULT,
    TTL_SUCCESS_DAYS_DEFAULT,
)


@dataclass(frozen=True, slots=True)
class RunRetention:
    pod_gc_delay_hours: int = POD_GC_DELAY_HOURS_DEFAULT
    ttl_success_days: int = TTL_SUCCESS_DAYS_DEFAULT
    ttl_failure_days: int = TTL_FAILURE_DAYS_DEFAULT
