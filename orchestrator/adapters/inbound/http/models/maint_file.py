from __future__ import annotations

from pydantic import BaseModel


class MaintFile(BaseModel):
    filename: str
    status: str
    additions: float
    deletions: float
    patch: str
