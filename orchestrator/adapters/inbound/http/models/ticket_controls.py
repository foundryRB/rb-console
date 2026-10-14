"""The maintenance control projection carried by the browser contract."""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.domain.model.ticket_next_act import TicketNextAct

__all__ = ["TicketControls"]


class TicketControls(BaseModel):
    next_act: TicketNextAct
    merge_blocked: str | None
    resolve_ran: bool
    pr_merged: bool
    default_stop: str
    delivery_scale: bool
    wrong_repo: bool
    can_switch_to_delivery: bool
