from __future__ import annotations

from pydantic import BaseModel


class ScopeComponent(BaseModel):
    phase: str
    layer: str
    component: str
    technology: str
    description: str
    scope: str
