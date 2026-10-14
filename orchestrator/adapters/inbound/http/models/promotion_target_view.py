from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PromotionTargetView(BaseModel):
    name: str
    kind: Literal["environment", "repository"]
    destination: str
    door: str
    terms: str
    acceptance: str
    state: Literal["unproven", "in-flight", "pending", "current", "unreadable"]
    accepted: str
    door_ref: str
    detail: str
    credential: str
    door_shut: bool
