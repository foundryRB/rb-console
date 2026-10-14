"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.driver_agent import DriverAgent


def helper_reject_invalid_credential(
    credential: str, model: str, base_url: str, *, driver: DriverAgent | None
) -> None:
    """The selection-time preflight (issue #30): exercise the credential through the same
    driver the co-pilot and the worker authenticate with, fail-closed only on an explicit
    401/403 answer. No driver wired, or a transport/timeout failure, is not evidence the
    credential is wrong (fail-open) - it is seated and the first real run will tell."""
    if driver is None:
        return
    valid = driver.validate(credential, model=model, base_url=base_url)
    if valid is False:
        raise ValueError(
            "credential rejected by the provider (check the key - 401/403)"
        )
