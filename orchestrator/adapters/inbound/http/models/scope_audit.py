from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.audit_suggestion import AuditSuggestion


class ScopeAudit(BaseModel):
    passed: bool
    passed_count: float
    failed_count: float
    suggestions: list[AuditSuggestion]
