from __future__ import annotations

from orchestrator.domain.model.studio_artifact import StudioArtifact
from orchestrator.domain.model.studio_health import StudioHealth


def studios_dto(healths: list[StudioHealth]) -> dict:
    """The org-wide view of everything: each connected studio's reachability + headline."""
    return {
        "studios": [
            {
                "studio": h.studio,
                "reachable": h.reachable,
                "detail": h.detail,
                "url": h.url,
            }
            for h in healths
        ]
    }


def _artifact_dto(a: StudioArtifact | None) -> dict | None:
    if a is None:
        return None
    return {
        "studio": a.studio,
        "reachable": a.reachable,
        "exists": a.exists,
        "url": a.url,
        "detail": a.detail,
    }
