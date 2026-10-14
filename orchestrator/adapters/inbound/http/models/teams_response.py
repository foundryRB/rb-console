from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.team import Team


class TeamsResponse(BaseModel):
    teams: list[Team]
