"""StudioArtifact domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioArtifact:
    """A delivery's artifact in one studio: does it exist, and where to see it."""

    studio: str
    reachable: bool  # the studio answered
    exists: bool | None  # artifact for this slug present; None when unreachable/unknown
    url: str | None  # deep link to the artifact, or the studio's own page
    detail: str = ""  # short human note ("12 screens", "audit passed", "running")
