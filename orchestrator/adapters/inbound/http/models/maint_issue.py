from __future__ import annotations

from pydantic import BaseModel


class MaintIssue(BaseModel):
    number: float
    title: str
    author: str
    labels: list[str]
    url: str
    created_at: str
    complexity: str
    priority: str
    type: str
