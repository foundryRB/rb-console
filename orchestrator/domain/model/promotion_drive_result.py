"""Accepted promotion execution identity."""

from dataclasses import dataclass

from orchestrator.domain.model.target_kind import TargetKind


@dataclass(frozen=True)
class PromotionDriveResult:
    run_id: str
    handle: str
    target: str
    release: str
    kind: TargetKind
