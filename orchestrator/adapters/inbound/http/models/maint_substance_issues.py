from __future__ import annotations

from pydantic import BaseModel


class MaintSubstanceIssues(BaseModel):
    number: float
    title: str
    url: str
