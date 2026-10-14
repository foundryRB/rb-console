"""The facts this console states on the platform event bus, and the one way to state one.

REF-Events gives each domain exactly one owner, and this console owns ``delivery``
and ``maintenance`` by its grant. The constants below are its whole vocabulary;
the docs page ``events.md`` states the same rows for consumers, and a test holds
the two equal so neither can drift (REF-Events section 3: each owner states its
own types, held by its own tests). A type is never composed at a call site.

Every row narrates something the console already does (P3: it adds no
capability): an act it performs (start, drive, sign, re-open, close, a
maintenance drive, merge or close), or an observation its refresh tick already
makes (a run turned terminal; a delivery's derived position moved; the one-shot
judge read a verdict and merged or parked). Positions stay derived from the
scratch and from the repo host (P2): an event says something happened and is
never read back as the state of a line. On a cold start the tick primes what it
sees and narrates nothing, so a restart never replays a history it merely found.

``state_fact`` is where the one-way rule is enforced for every caller at once. A
publisher is contractually forbidden from raising, but a caller that trusted that
contract and was wrong would fail the act it had already committed, which is the
single failure REF-Events section 6 exists to prevent (ADR-038 is the console's
own precedent). So the guarantee is made true here rather than assumed.
"""

from __future__ import annotations

import logging

from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.domain.delivery import (
    AWAITING_GATE,
    DEGRADED,
    DELIVERED,
    LEARNED,
    NOT_A_DELIVERY,
    RUN_PHASE,
)
from orchestrator.domain.model.delivery_state import DeliveryState

__all__ = [
    "ACT_LAUNCHED",
    "ACT_PARKED",
    "GATE_REACHED",
    "GATE_SIGNED",
    "LINE_CLOSED",
    "LINE_DELIVERED",
    "LINE_LEARNED",
    "LINE_STARTED",
    "PHASE_ENTERED",
    "PHASE_REOPENED",
    "PHASE_STARTED",
    "PR_JUDGED",
    "PR_MERGED",
    "RUN_COMPLETED",
    "RUN_DEGRADED",
    "TICKET_CLOSED",
    "position_facts",
    "state_fact",
]

logger = logging.getLogger(__name__)

# The delivery domain: the line this console drives.
LINE_STARTED = "com.foundry.delivery.line.started"
PHASE_STARTED = "com.foundry.delivery.phase.started"
PHASE_ENTERED = "com.foundry.delivery.phase.entered"
GATE_REACHED = "com.foundry.delivery.gate.reached"
GATE_SIGNED = "com.foundry.delivery.gate.signed"
PHASE_REOPENED = "com.foundry.delivery.phase.reopened"
RUN_COMPLETED = "com.foundry.delivery.run.completed"
RUN_DEGRADED = "com.foundry.delivery.run.degraded"
LINE_DELIVERED = "com.foundry.delivery.line.delivered"
LINE_LEARNED = "com.foundry.delivery.line.learned"
LINE_CLOSED = "com.foundry.delivery.line.closed"

# The maintenance domain: the ticket loop this console drives and judges.
ACT_LAUNCHED = "com.foundry.maintenance.act.launched"
PR_JUDGED = "com.foundry.maintenance.pr.judged"
PR_MERGED = "com.foundry.maintenance.pr.merged"
ACT_PARKED = "com.foundry.maintenance.act.parked"
TICKET_CLOSED = "com.foundry.maintenance.ticket.closed"


def state_fact(
    publisher: EventPublisher | None,
    *,
    event_type: str,
    subject: str,
    data: dict[str, object],
) -> None:
    """Publish a fact, and let nothing about it reach the caller.

    Every failure mode ends the same way: dropped, logged at warning, and the
    act that caused it completes with the outcome it already had. No publisher
    wired (a console with no bus grant) states nothing and logs nothing.
    """
    if publisher is None:
        return
    try:
        publisher.publish(event_type=event_type, subject=subject, data=data)
    except Exception as exc:  # noqa: BLE001  a publish never fails its cause
        logger.warning("dropped event %s for %s: %s", event_type, subject, exc)


def position_facts(
    before: DeliveryState | None, after: DeliveryState
) -> list[tuple[str, dict[str, object]]]:
    """The facts a delivery's derived position states by moving between two reads.

    The position is the pair (status, phase) the resolver derives from the
    scratch's records. A read that finds it unchanged states nothing; a first
    read (no ``before``) states nothing either, because a cold start found a
    history rather than watched a change, and a line's birth is the act
    ``line.started`` narrates. Each destination status is one type, so a consumer
    subscribes to the fact it reacts to (a degraded run, a reached gate) rather
    than filtering every move.
    """
    if before is None or before.status == NOT_A_DELIVERY:
        return []
    if (before.status, before.phase) == (after.status, after.phase):
        return []
    data: dict[str, object] = {
        "repo": after.repo,
        "phase": after.phase,
        "previous_status": before.status,
        "previous_phase": before.phase,
    }
    if after.status == RUN_PHASE:
        return [(PHASE_ENTERED, data)]
    if after.status == AWAITING_GATE:
        return [(GATE_REACHED, {**data, "gate": after.blocked_gate})]
    if after.status == DEGRADED:
        return [(RUN_DEGRADED, data)]
    if after.status == DELIVERED:
        return [(LINE_DELIVERED, data)]
    if after.status == LEARNED:
        return [(LINE_LEARNED, {**data, "learned_on": after.learned_on})]
    return []
