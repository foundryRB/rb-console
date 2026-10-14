from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.maint_issue import MaintIssue
from orchestrator.adapters.inbound.http.models.maint_pr import MaintPr
from orchestrator.adapters.inbound.http.models.maint_train import MaintTrain


class MaintPositions(BaseModel):
    repo: str
    issues: list[MaintIssue]
    prs: list[MaintPr]
    train: MaintTrain
    recent_closed: list[MaintPr]
