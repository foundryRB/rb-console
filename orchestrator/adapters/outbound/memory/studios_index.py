"""Warm cache of cross-studio status, refreshed out of band like the DeliveryIndex so
a page load never hits the studios. The background refresher populates it; reads serve
whatever was last cached. A studio that is down leaves its last-known (or empty) entry
rather than failing the read.
"""

from __future__ import annotations

import logging

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.studio_artifact import StudioArtifact
from orchestrator.domain.model.studio_health import StudioHealth


class StudioStatusIndex:
    def __init__(self) -> None:
        self._health: list[StudioHealth] = []
        self._artifacts: dict[str, dict[str, StudioArtifact]] = {}

    def refresh(self, gateway: StudioGateway, slugs: list[str]) -> int:
        """Rescan every studio's health and each delivery slug's artifacts into the
        cache. Called by the background refresher, never on a read."""
        failed = False
        try:
            self._health = gateway.health()
        except Exception:
            failed = True
            logging.getLogger(__name__).warning(
                "Studio health observation failed", exc_info=True
            )
        arts = dict(self._artifacts)
        for slug in slugs:
            try:
                arts[slug] = gateway.artifacts_for(slug)
            except Exception:
                failed = True
                logging.getLogger(__name__).warning(
                    "Studio artifacts observation failed for %s", slug, exc_info=True
                )
        self._artifacts = arts
        if failed:
            raise SourceUnavailable("Studio observation coverage is incomplete")
        return len(arts)

    def health(self) -> list[StudioHealth]:
        return list(self._health)

    def artifacts(self, slug: str) -> dict[str, StudioArtifact]:
        return dict(self._artifacts.get(slug, {}))
