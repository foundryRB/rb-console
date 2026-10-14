from __future__ import annotations

from pydantic import BaseModel


class AuditSuggestion(BaseModel):
    title: str
    detail: str
    severity: str
    category: str
