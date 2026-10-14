from __future__ import annotations

from pydantic import BaseModel


class ScopeGuideline(BaseModel):
    id: str
    group: str
    name: str
    description: str
    rationale: str
