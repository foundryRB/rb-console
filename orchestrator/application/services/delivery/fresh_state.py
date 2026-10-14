"""Delivery shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.delivery_state import DeliveryState


def helper_fresh_state(
    repo: str, *, source: DeliverySource | None, cap_status: StatusPort
) -> DeliveryState:
    """Source truth for ACTIONS. The warm index serves reads; an action that follows a
    state-changing act in the same breath (sign then drive, re-open then sign) must read
    the world, or it acts on the cache - a live e2e re-ran a finished phase that way."""
    if source is None:
        raise SourceUnavailable(
            "An authoritative delivery source is required for this action"
        )
    return source.state_of(repo)
