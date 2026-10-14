from __future__ import annotations

from pydantic import BaseModel


class FleetItem(BaseModel):
    repo: str
    name: str
    app_name: str
    host: str
    is_delivery: bool
    delivery_status: str | None
    delivery_phase: str | None
    onboarded: bool
    live: str | None
    updated: str | None
    estimatekit: bool
    protopane: bool
    hidden: bool
    role: str | None
    activity: str | None
