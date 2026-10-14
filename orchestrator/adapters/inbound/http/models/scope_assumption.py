from __future__ import annotations

from pydantic import BaseModel


class ScopeAssumption(BaseModel):
    id: str
    group: str
    title: str
    assumption: str
    confidence: str
    impact: str
    req_ids: list[str]
