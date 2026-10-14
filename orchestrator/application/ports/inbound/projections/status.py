"""Status application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.delivery_state import DeliveryState


@runtime_checkable
class StatusPort(Protocol):
    def execute(self, repo: str) -> DeliveryState: ...
