from __future__ import annotations

from pydantic import BaseModel


class DriverInfo(BaseModel):
    base_url: str
    model: str
    configured: bool
    agent: str
