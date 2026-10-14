"""Semantic committed delivery record value."""
from dataclasses import dataclass

from orchestrator.domain.model.frontmatter import Frontmatter


@dataclass(frozen=True)
class DeliveryRecord:
    frontmatter: Frontmatter | None = None
