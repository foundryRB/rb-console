from __future__ import annotations

from pydantic import BaseModel


class ScopeActivity(BaseModel):
    id: str
    phase: str
    group: str
    activity: str
    effort_md: float
    req_ids: list[str]
    description: str
