from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.maint_file import MaintFile
from orchestrator.adapters.inbound.http.models.maint_review import MaintReview
from orchestrator.adapters.inbound.http.models.maint_substance_issues import (
    MaintSubstanceIssues,
)
from orchestrator.adapters.inbound.http.models.maint_substance_releases import (
    MaintSubstanceReleases,
)


class MaintSubstance(BaseModel):
    kind: str
    number: float = None
    title: str = None
    author: str = None
    labels: list[str] = None
    body: str = None
    url: str = None
    head: str = None
    verdict: str = None
    checks: str = None
    contributor: bool = None
    files: list[MaintFile] = None
    reviews: list[MaintReview] = None
    issues: list[MaintSubstanceIssues] = None
    log: str = None
    releases: list[MaintSubstanceReleases] = None
    deployed: str = None
    healthy: bool | None = None
