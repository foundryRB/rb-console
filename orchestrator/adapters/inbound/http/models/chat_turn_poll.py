from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.fleet_item import FleetItem
from orchestrator.adapters.inbound.http.models.freshness import Freshness


class ChatTurnPoll(BaseModel):
    status: str
    reply: str | None = None
    configured: bool = None
    model: str | None = None
    projects: list[FleetItem] = None
    stale_since: str | None = None
    stale_reason: str = None
    freshness: Freshness | None = None
    error: str = None
