from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.run_node import RunNode


class RunGraph(BaseModel):
    name: str = None
    phase: str
    stop: str | None = None
    progress: str | None = None
    nodes: list[RunNode]

    freshness: Freshness | None = None
