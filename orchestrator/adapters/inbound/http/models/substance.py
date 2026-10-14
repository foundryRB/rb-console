from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.intent_claim import IntentClaim
from orchestrator.adapters.inbound.http.models.proto_screen import ProtoScreen
from orchestrator.adapters.inbound.http.models.scope_activity import ScopeActivity
from orchestrator.adapters.inbound.http.models.scope_architecture import (
    ScopeArchitecture,
)
from orchestrator.adapters.inbound.http.models.scope_assumption import ScopeAssumption
from orchestrator.adapters.inbound.http.models.scope_audit import ScopeAudit
from orchestrator.adapters.inbound.http.models.scope_estimate import ScopeEstimate
from orchestrator.adapters.inbound.http.models.scope_phase import ScopePhase
from orchestrator.adapters.inbound.http.models.scope_requirement import ScopeRequirement
from orchestrator.adapters.inbound.http.models.scope_summary import ScopeSummary


class Substance(BaseModel):
    summary: ScopeSummary = None
    audit: ScopeAudit = None
    requirements: list[ScopeRequirement] = None
    phases: list[ScopePhase] = None
    assumptions: list[ScopeAssumption] = None
    activities: list[ScopeActivity] = None
    estimate: ScopeEstimate = None
    architecture: ScopeArchitecture = None
    theme_css: str = None
    screens: list[ProtoScreen] = None
    canvas_js: str = None
    canvas_css: str = None
    claims: list[IntentClaim] = None
