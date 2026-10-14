from typing import Literal

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.coverage import Coverage


class Freshness(BaseModel):
    state: Literal["loading", "fresh", "stale", "unavailable"]
    observed_at: str | None
    last_attempt_at: str | None
    reason_code: str
    coverage: Coverage
    age_seconds: float | None = None
