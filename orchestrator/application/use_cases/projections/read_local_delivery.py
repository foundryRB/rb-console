"""Observe a local delivery for the explicit CLI status command."""

from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.domain.model.delivery_state import DeliveryState


class ReadLocalDelivery:
    def __init__(self, source: DeliverySource) -> None:
        self.source = source

    def execute(self, repository: str) -> DeliveryState:
        return self.source.state_of(repository)
