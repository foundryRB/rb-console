from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.studio_artifact import StudioArtifact


class PhaseView(BaseModel):
    name: str
    question: str
    skill: str
    studio: str | None
    gate: str | None
    gate_signed_on: str | None
    record: str | None
    record_present: bool
    is_current: bool
    needs_review: bool
    artifact: StudioArtifact | None

    tone: Literal["done", "running", "failed", "warn", "current", "locked"] = "locked"
    sub_label: str = ""
    renderer: str = "record"
