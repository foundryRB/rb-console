from __future__ import annotations

from pydantic import BaseModel


class ScopeEstimatePhases(BaseModel):
    id: str
    effort_md: float
