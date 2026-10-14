from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.install_option import InstallOption


class PromotionOptions(BaseModel):
    repo: str
    readable: bool
    installs: list[InstallOption]

    freshness: Freshness | None = None
