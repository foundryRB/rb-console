from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.state import State


class DriveResult(BaseModel):
    run_id: str
    handle: str | None
    state: State
    steps: list[str]
