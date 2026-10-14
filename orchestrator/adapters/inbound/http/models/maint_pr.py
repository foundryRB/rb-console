from __future__ import annotations

from pydantic import BaseModel


class MaintPr(BaseModel):
    number: float
    title: str
    author: str
    head: str
    head_sha: str
    url: str
    verdict: str
    checks: str
    contributor: bool
    updated_at: str
    state: str
