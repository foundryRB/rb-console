from __future__ import annotations

from orchestrator.adapters.inbound.http.models.delivery_config import DeliveryConfig
from orchestrator.adapters.inbound.http.models.delivery_controls import DeliveryControls
from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.phase_view import PhaseView
from orchestrator.adapters.inbound.http.models.state import State


class Overview(State):
    config: DeliveryConfig
    phases: list[PhaseView]

    freshness: Freshness | None = None
    controls: DeliveryControls
