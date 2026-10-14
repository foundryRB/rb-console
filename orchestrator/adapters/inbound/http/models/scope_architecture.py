from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.scope_component import ScopeComponent
from orchestrator.adapters.inbound.http.models.scope_diagram import ScopeDiagram
from orchestrator.adapters.inbound.http.models.scope_guideline import ScopeGuideline


class ScopeArchitecture(BaseModel):
    guidelines: list[ScopeGuideline] = None
    components: list[ScopeComponent] = None
    diagrams: list[ScopeDiagram] = None
