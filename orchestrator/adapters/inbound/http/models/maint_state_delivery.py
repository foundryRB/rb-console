from __future__ import annotations

from pydantic import BaseModel


class MaintStateDelivery(BaseModel):
    status: str
    phase: str | None
