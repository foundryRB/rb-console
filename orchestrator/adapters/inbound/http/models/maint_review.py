from __future__ import annotations

from pydantic import BaseModel


class MaintReview(BaseModel):
    author: str
    submitted_at: str
    body: str
