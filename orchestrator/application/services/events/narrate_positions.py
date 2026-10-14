"""Events shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.events import position_facts, state_fact
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)


def helper_narrate_positions(
    *,
    observations: ObservationStore,
    events: EventPublisher | None,
    index: DeliveryIndex | None,
) -> None:
    """State each delivery whose derived position moved since the last tick. The
    first tick primes the cache and states nothing: a cold start found a history,
    it did not watch a change."""
    if index is None:
        return
    current = {s.repo: s for s in index.all()}
    if observations.positions:
        for repo, after in current.items():
            for event_type, data in position_facts(
                observations.positions.get(repo), after
            ):
                state_fact(events, event_type=event_type, subject=repo, data=data)
    observations.positions = current
