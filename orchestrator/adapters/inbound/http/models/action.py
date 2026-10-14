from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.action_kind import ActionKind
from orchestrator.adapters.inbound.http.models.launch import Launch
from orchestrator.adapters.inbound.http.models.state import State


class Action(BaseModel):
    kind: ActionKind
    gate: str | None
    state: State
    launch: Launch = None
