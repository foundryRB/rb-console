from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.fleet_item import FleetItem
from orchestrator.adapters.inbound.http.models.freshness import Freshness


class FleetResponse(BaseModel):
    projects: list[FleetItem]
    stale_since: str | None = None
    stale_reason: str = None

    freshness: Freshness | None = None
