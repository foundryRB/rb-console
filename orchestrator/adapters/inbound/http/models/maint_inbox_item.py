from __future__ import annotations

from pydantic import BaseModel


class MaintInboxItem(BaseModel):
    repo: str
    signal: str
    detail: str
    act: str
    number: float | None
    ts: str
    hidden: bool
    stage: str
