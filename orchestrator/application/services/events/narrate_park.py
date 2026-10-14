"""Events shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.events import ACT_PARKED, state_fact
from orchestrator.application.ports.outbound.event_publisher import EventPublisher


def helper_narrate_park(
    *, repo_ticket: dict, handle: str, reason: str, events: EventPublisher | None
) -> None:
    """State that a one-shot act parked for the operator, with the judge's own words."""
    state_fact(
        events,
        event_type=ACT_PARKED,
        subject=str(repo_ticket.get("repo") or ""),
        data={
            "repo": repo_ticket.get("repo"),
            "ticket": repo_ticket.get("ticket"),
            "handle": handle,
            "reason": reason,
        },
    )
