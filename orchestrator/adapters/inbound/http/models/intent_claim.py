from __future__ import annotations

from pydantic import BaseModel


class IntentClaim(BaseModel):
    id: str
    status: str
    criticality: str
    statement: str
