from __future__ import annotations

from pydantic import BaseModel


class MaintDriven(BaseModel):
    handle: str
    repo: str
    ticket: float
    acted: bool
    result: str
