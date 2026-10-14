from __future__ import annotations

from pydantic import BaseModel


class ScopePhase(BaseModel):
    id: str
    phase: str
    name: str
    description: str
    requirement_ids: list[str]
