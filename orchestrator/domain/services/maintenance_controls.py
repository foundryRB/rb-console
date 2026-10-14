"""Maintenance controls from current reviews, checks and recorded ticket progress."""
from __future__ import annotations

from orchestrator.domain.maintenance import (
    CHECKS_GREEN,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_UNRECORDED,
)
from orchestrator.domain.model.pr_position import PrPosition
from orchestrator.domain.model.ticket_controls import TicketControls
from orchestrator.domain.model.ticket_next_act import TicketNextAct

__all__ = ["derive_ticket_controls"]


def derive_ticket_controls(
    open_pr: PrPosition | None,
    closed_pr: PrPosition | None,
    resolve_ran: bool,
    default_stop: str,
    delivery_scale: bool = False,
    wrong_repo: bool = False,
    can_switch_to_delivery: bool = False,
) -> TicketControls:
    merged = closed_pr is not None and closed_pr.state == "merged"
    blocked = None
    if open_pr:
        if open_pr.verdict != VERDICT_PASS:
            if open_pr.verdict == VERDICT_FAIL:
                blocked = "the verdict is FAIL - the findings are the work order"
            elif open_pr.verdict == VERDICT_UNRECORDED:
                blocked = "the review is UNRECORDED - the PR awaits an independent reviewer"
            else:
                blocked = "no fresh-eyes PASS yet - nothing merges unreviewed"
        elif open_pr.checks != CHECKS_GREEN:
            blocked = f"checks are {open_pr.checks} - a red CI blocks the merge in every mode"
    if merged:
        next_act = TicketNextAct.CLOSE
    elif open_pr is None or open_pr.verdict == VERDICT_FAIL:
        next_act = TicketNextAct.RESOLVE
    elif open_pr.verdict == VERDICT_PASS:
        next_act = TicketNextAct.MERGE
    else:
        next_act = TicketNextAct.REVIEW
    return TicketControls(
        next_act=next_act,
        merge_blocked=blocked,
        resolve_ran=resolve_ran,
        pr_merged=merged,
        default_stop=default_stop,
        delivery_scale=delivery_scale,
        wrong_repo=wrong_repo,
        can_switch_to_delivery=can_switch_to_delivery,
    )
