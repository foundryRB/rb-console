"""Projections shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.services.delivery.fresh_state import helper_fresh_state
from orchestrator.domain.model.delivery_state import DeliveryState


def helper_remember(
    repo: str,
    *,
    index: DeliveryIndex | None,
    source: DeliverySource | None,
    cap_status: StatusPort,
) -> DeliveryState:
    """Fresh state after a mutating act, written through to the index
    (read-your-write). Without the write-through, the next poll re-reads the pre-act
    cache and the act looks undone until the background rescan: a signed gate
    un-signed itself on screen for a minute that way."""
    state = partial(helper_fresh_state, source=source, cap_status=cap_status)(repo)
    if index is not None:
        index.put(state)
    return state
