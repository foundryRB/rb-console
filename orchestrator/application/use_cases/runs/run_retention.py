"""RunRetention over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.settings.get_setting import GetSettingPort
from orchestrator.application.services.definitions import _RETENTION_SETTING
from orchestrator.domain.services.run_policy import (
    POD_GC_DELAY_HOURS_DEFAULT,
    TTL_FAILURE_DAYS_DEFAULT,
    TTL_SUCCESS_DAYS_DEFAULT,
)


class RunRetention:
    def __init__(self, *, cap_get_setting: GetSettingPort) -> None:
        self.cap_get_setting = cap_get_setting

    def execute(self) -> dict:
        """The operator's Run retention setting (the Settings page's generic
        'run-retention' setting), clamped sane: pod_gc_delay_hours is how long a finished
        run's pods - and so its live logs - outlive it; ttl_success_days / ttl_failure_days
        are how long its row stays listable in the band. Defaults hold for anything unset
        or unparsable, and the failure TTL never clamps below the success TTL, so a failed
        run is never the shorter-lived record (INT-FC-R110)."""
        stored = self.cap_get_setting.execute(_RETENTION_SETTING)

        def _val(key: str, default: int, lo: int, hi: int) -> int:
            try:
                return max(
                    lo, min(hi, int(str(stored.get(key, "")).strip() or default))
                )
            except (TypeError, ValueError):
                return default

        success = _val("ttl_success_days", TTL_SUCCESS_DAYS_DEFAULT, 1, 90)
        return {
            "pod_gc_delay_hours": _val(
                "pod_gc_delay_hours", POD_GC_DELAY_HOURS_DEFAULT, 1, 48
            ),
            "ttl_success_days": success,
            "ttl_failure_days": max(
                success, _val("ttl_failure_days", TTL_FAILURE_DAYS_DEFAULT, 1, 90)
            ),
        }
