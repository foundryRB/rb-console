from __future__ import annotations

from pydantic import BaseModel


class ScopeDiagram(BaseModel):
    name: str
    phase: str
    puml: str
    svg: str = None
