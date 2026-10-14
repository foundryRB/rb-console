from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.studio_health import StudioHealth


class StudiosResponse(BaseModel):
    studios: list[StudioHealth]

    freshness: Freshness | None = None
