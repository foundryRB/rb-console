"""Studios shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.definitions import logger
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.exceptions.studio_tool_error import StudioToolError
from orchestrator.domain.model.catalog_agent import CatalogAgent


def helper_agent_catalog(*, studios: StudioGateway | None) -> dict[str, CatalogAgent]:
    if studios is None:
        return {}
    try:
        roster = studios.agent_catalog()
    except (SourceUnavailable, StudioToolError, OSError) as exc:
        logger.warning(
            "agent catalog unreachable (%s); workers run with no catalog posture or character",
            exc,
        )
        return {}
    catalog = {a.name: a for a in roster}
    if not catalog:
        logger.warning(
            "agent catalog is empty or unreachable; workers run with no catalog posture or character"
        )
    return catalog
