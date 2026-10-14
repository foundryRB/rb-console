from __future__ import annotations

from typing import Protocol

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.domain.model.studio_artifact import StudioArtifact
from orchestrator.domain.model.studio_health import StudioHealth


class StudioStatusIndex(Protocol):
    def refresh(self, gateway: StudioGateway, slugs: list[str]) -> int: ...

    def health(self) -> list[StudioHealth]: ...

    def artifacts(self, slug: str) -> dict[str, StudioArtifact]: ...
