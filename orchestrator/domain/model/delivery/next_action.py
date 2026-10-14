"""Delivery execution result."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.worker_launch import WorkerLaunch


@dataclass(frozen=True)
class NextAction:
    """What the orchestrator would do next for a delivery."""
    kind: str
    state: DeliveryState
    launch: WorkerLaunch | None = None
    gate: str | None = None
    handle: str | None = None
