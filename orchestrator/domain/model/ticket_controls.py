"""Observed maintenance actions and their availability."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.ticket_next_act import TicketNextAct

__all__ = ["TicketControls"]


@dataclass(frozen=True)
class TicketControls:
    next_act: TicketNextAct
    merge_blocked: str | None
    resolve_ran: bool
    pr_merged: bool
    default_stop: str
    delivery_scale: bool
    wrong_repo: bool
    can_switch_to_delivery: bool
