"""DeliveryOverview application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.delivery_overview import DeliveryOverview


@runtime_checkable
class DeliveryOverviewPort(Protocol):
    def execute(self, repo: str) -> DeliveryOverview: ...
