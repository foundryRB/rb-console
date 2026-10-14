from __future__ import annotations

from pydantic import BaseModel


class TreeEntry(BaseModel):
    path: str
    type: str
    size: float | None
