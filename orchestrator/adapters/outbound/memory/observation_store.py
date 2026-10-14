"""Process-local observations with serialized publication."""

from __future__ import annotations

from threading import Lock

from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.fleet_item import FleetItem
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry


class MemoryObservationStore:
    def __init__(self) -> None:
        self.runs: list[RunInventoryEntry] = []
        self.graphs: dict[str, ExecutionGraph] = {}
        self.positions: dict[str, DeliveryState] = {}
        self.terminal_seen: set[str] | None = None
        self.fleet: list[FleetItem] = []
        self.fleet_stale_since: str | None = None
        self.fleet_stale_reason = ""
        self.delivery_stale_since: str | None = None
        self.delivery_stale_reason = ""
        self.delivery_observed_at: str | None = None
        self.inbox: list[dict] = []
        self.inbox_tick = 0
        self.oneshot: dict[str, dict] = {}
        self.refresh_lock = Lock()
        self.metadata: dict[str, dict[str, object]] = {}

    def scope(self, repo: str):
        from orchestrator.adapters.outbound.memory.scoped_observation_store import (
            ScopedObservationStore,
        )

        return ScopedObservationStore(self, repo)
