from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.agent import Agent


class AgentsResponse(BaseModel):
    agents: list[Agent]
