from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.run import Run


class RunsResponse(BaseModel):
    runs: list[Run]

    freshness: Freshness | None = None
