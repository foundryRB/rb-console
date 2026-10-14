from __future__ import annotations

from pydantic import BaseModel


class ScopeRequirement(BaseModel):
    id: str
    category: str
    description: str
    phases: list[str]
