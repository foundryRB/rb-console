from __future__ import annotations

from pydantic import BaseModel


class MaintSubstanceReleases(BaseModel):
    tag: str
    name: str
    published_at: str
    url: str
