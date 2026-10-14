from __future__ import annotations

from pydantic import BaseModel


class MaintStateHome(BaseModel):
    repo: str
    branch: str
    credential: str
