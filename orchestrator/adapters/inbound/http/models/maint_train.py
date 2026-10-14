from __future__ import annotations

from pydantic import BaseModel


class MaintTrain(BaseModel):
    version: str
    unreleased_total: float
    breaking: float
    feat: float
    fix: float
    other: float
    next_version: str
    deployed: str
    healthy: bool | None
    checks: str
