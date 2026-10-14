from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.promotion_target_view import (
    PromotionTargetView,
)


class PromotionState(BaseModel):
    repo: str
    declared: bool
    problem: str
    proven: str
    subject: Literal["", "managed", "nothing-proven"] = ""
    targets: list[PromotionTargetView]

    freshness: Freshness | None = None
