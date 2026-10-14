"""Immutable AgentBinding worker input."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.catalog import agent_title
from orchestrator.domain.model.catalog_agent import CatalogAgent


@dataclass(frozen=True)
class AgentBinding:
    """A catalog agent's identity and execution posture for one compiled step."""

    name: str
    catalog: CatalogAgent | None = None

    @property
    def title(self) -> str:
        return self.catalog.title if self.catalog is not None else agent_title(self.name)
