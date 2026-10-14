from __future__ import annotations

from pydantic import BaseModel


class ScopeSummary(BaseModel):
    name: str = None
    client: str = None
    description: str = None
    phase_count: float = None
    requirement_count: float = None
    assumption_count: float = None
