from __future__ import annotations

from pydantic import BaseModel


class StudioHealth(BaseModel):
    studio: str
    reachable: bool
    detail: str
    url: str | None
