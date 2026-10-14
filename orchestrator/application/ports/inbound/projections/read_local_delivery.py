"""The local status entry point consumes an authoritative delivery reader."""

from typing import Protocol

from orchestrator.domain.model.delivery_state import DeliveryState


class ReadLocalDeliveryPort(Protocol):
    def execute(self, repository: str) -> DeliveryState: ...
