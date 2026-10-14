from __future__ import annotations

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.freshness import Freshness
from orchestrator.adapters.inbound.http.models.maint_driven import MaintDriven
from orchestrator.adapters.inbound.http.models.maint_positions import MaintPositions
from orchestrator.adapters.inbound.http.models.maint_pr import MaintPr
from orchestrator.adapters.inbound.http.models.maint_state_action import (
    MaintStateAction,
)
from orchestrator.adapters.inbound.http.models.maint_state_delivery import (
    MaintStateDelivery,
)
from orchestrator.adapters.inbound.http.models.maint_state_home import MaintStateHome
from orchestrator.adapters.inbound.http.models.ticket_cell import TicketCell
from orchestrator.adapters.inbound.http.models.ticket_controls import TicketControls


class MaintState(BaseModel):
    repo: str
    positions: MaintPositions | None
    action: MaintStateAction
    delivery: MaintStateDelivery
    driven: list[MaintDriven]
    home: MaintStateHome | None

    ticket_lines: dict[str, list[TicketCell]] = {}
    linked_pr: dict[str, MaintPr | None] = {}
    closed_pr: dict[str, MaintPr | None] = {}
    revision: str = ""
    freshness: Freshness | None = None
    ticket_controls: dict[str, TicketControls] = {}
