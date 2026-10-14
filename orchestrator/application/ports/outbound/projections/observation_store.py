"""Transient observed state shared by the collection and query capabilities."""

from __future__ import annotations

from threading import Lock
from typing import Protocol

from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.fleet_item import FleetItem
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


class ObservationStore(Protocol):
    runs: list[RunInventoryEntry]
    graphs: dict[str, ExecutionGraph]
    positions: dict[str, DeliveryState]
    terminal_seen: set[str] | None
    fleet: list[FleetItem]
    fleet_stale_since: str | None
    fleet_stale_reason: str
    delivery_stale_since: str | None
    delivery_stale_reason: str
    delivery_observed_at: str | None
    inbox: list[dict]
    inbox_tick: int
    oneshot: dict[str, dict]
    refresh_lock: Lock
    metadata: dict[str, dict[str, object]]

    def scope(self, repo: str) -> ObservationStore: ...
