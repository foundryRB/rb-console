from __future__ import annotations

from typing import Protocol

from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.domain.model.delivery_state import DeliveryState


class DeliveryIndex(Protocol):
    @property
    def scanned(self) -> bool: ...

    def refresh(self, source: DeliverySource) -> int: ...

    def all(self) -> list[DeliveryState]: ...

    def get(self, repo: str) -> DeliveryState | None: ...

    def put(self, state: DeliveryState) -> None: ...
