from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.scope_estimate_phases import (
    ScopeEstimatePhases,
)


class ScopeEstimate(BaseModel):
    phases: list[ScopeEstimatePhases]
    total_md: float
