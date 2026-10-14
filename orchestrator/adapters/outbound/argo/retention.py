"""Render evidence retention for the Argo executor."""

from orchestrator.domain.services.run_policy import (
    POD_GC_DELAY_HOURS_DEFAULT,
    TTL_FAILURE_DAYS_DEFAULT,
    TTL_SUCCESS_DAYS_DEFAULT,
)

_POD_GC_STRATEGY = "OnWorkflowCompletion"


def gc_policy(
    *,
    pod_gc_delay_hours: int = POD_GC_DELAY_HOURS_DEFAULT,
    ttl_success_days: int = TTL_SUCCESS_DAYS_DEFAULT,
    ttl_failure_days: int = TTL_FAILURE_DAYS_DEFAULT,
) -> dict:
    """The pod- and Workflow-GC block every compiled Workflow carries, so no finished run
    strands its worker pods (INT-FC-R95). Both compilers splice it into ``spec``; fresh dicts
    each call so a caller can never mutate the shared policy into another workflow's spec.
    The horizons are parameters because they are the operator's Run retention setting
    (INT-FC-R110): the service reads the stored setting per compile and passes it down;
    the defaults here are what an unconfigured console runs."""
    return {
        "podGC": {
            "strategy": _POD_GC_STRATEGY,
            "deleteDelayDuration": f"{pod_gc_delay_hours}h",
        },
        "ttlStrategy": {
            "secondsAfterSuccess": ttl_success_days * 86400,
            "secondsAfterFailure": ttl_failure_days * 86400,
        },
    }
