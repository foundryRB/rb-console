from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.state import State


class DeliveriesResponse(BaseModel):
    deliveries: list[State]

    freshness: Freshness | None = None
