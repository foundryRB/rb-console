from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.delivery_status import DeliveryStatus
from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.gate import Gate
from orchestrator.adapters.inbound.http.models.phase_cell import PhaseCell
from orchestrator.adapters.inbound.http.models.seed import Seed


class State(BaseModel):
    repo: str
    exists: bool
    status: DeliveryStatus
    phase: str | None
    next_skill: str | None
    next_command: str | None
    blocked_gate: str | None
    gates: list[Gate]
    records_present: list[str]
    learned_on: str | None
    seed: Seed = None
    demo_of: str = None

    phase_cells: list[PhaseCell] = []
    pending_gate: str | None = None
    status_label: str = ""
    revision: str = ""
    freshness: Freshness | None = None
