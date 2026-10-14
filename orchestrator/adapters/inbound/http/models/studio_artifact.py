from __future__ import annotations

from pydantic import BaseModel


class StudioArtifact(BaseModel):
    studio: str
    reachable: bool
    exists: bool | None
    url: str | None
    detail: str
