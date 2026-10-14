"""Operator controls follow observed records, run stops and independent verdicts."""
from __future__ import annotations

import pytest

from orchestrator.domain.model.pr_position import PrPosition
from orchestrator.domain.services.delivery_controls import derive_delivery_controls
from orchestrator.domain.services.maintenance_controls import derive_ticket_controls


@pytest.mark.parametrize(
    ("phase", "primary", "in_flight"),
    [("Suspended", "resume", True), ("Running", "running", True),
     ("Stopping", "running", True), ("Stopped", "redrive", False),
     ("Failed", "redrive", False), ("Succeeded", "drive", False)],
)
def test_learned_line_retains_close_and_its_contextual_run_control(
    phase: str, primary: str, in_flight: bool,
) -> None:
    controls = derive_delivery_controls("learned", "run-1", phase, {"wrap": False}, "wrap")
    assert controls.primary_kind == primary
    assert controls.run_in_flight is in_flight
    assert controls.can_close
    assert controls.phase_has_run["wrap"]
    assert controls.close_is_next is (primary == "drive")


def test_parked_unsigned_gate_is_signable_and_unavailable_observation_is_not_actionable() -> None:
    parked = derive_delivery_controls("awaiting-gate", "run-1", "Suspended", {})
    unavailable = derive_delivery_controls("unavailable", None, None, {})
    assert parked.can_sign
    assert not unavailable.can_close
    assert unavailable.primary_kind == "unavailable"


@pytest.mark.parametrize(
    ("verdict", "checks", "next_act", "blocked"),
    [("pass", "green", "merge", False), ("pass", "unknown", "merge", True),
     ("fail", "green", "resolve", True), ("unrecorded", "green", "review", True)],
)
def test_merge_availability_requires_independent_pass_and_current_green_checks(
    verdict: str, checks: str, next_act: str, blocked: bool,
) -> None:
    pr = PrPosition(2, "fix(#1): correction", "worker", verdict=verdict, checks=checks)
    controls = derive_ticket_controls(pr, None, True, "review")
    assert controls.next_act == next_act
    assert bool(controls.merge_blocked) is blocked


def test_a_landed_resolve_wants_close_and_a_closed_unmerged_resolve_wants_work() -> None:
    merged = PrPosition(2, "fix(#1): correction", "worker", state="merged")
    closed = PrPosition(3, "fix(#1): correction", "worker", state="closed")
    assert derive_ticket_controls(None, merged, True, "merge").next_act == "close"
    assert derive_ticket_controls(None, closed, True, "review").next_act == "resolve"


@pytest.mark.parametrize(("verdict", "detail"), [("pass", "PASS"), ("fail", "FAIL"), ("unrecorded", "unrecorded"), ("unexpected", "awaiting")])
def test_ticket_projection_preserves_short_labels_without_claiming_an_unknown_verdict(verdict, detail):
    from dataclasses import asdict

    from orchestrator.domain.services.maintenance.ticket_presentation import (
        ticket_presentation,
    )
    pr = PrPosition(2, "fix(#1): correction", "worker", verdict=verdict, checks="green", head="fix/1-correction")
    state = {"repo": "org/app", "positions": {"issues": [{"number": 1}], "prs": [asdict(pr)]}}
    projected = ticket_presentation(state, [])
    assert projected["ticket_lines"]["1"][2]["detail"] == detail
    if verdict != "pass":
        assert projected["ticket_lines"]["1"][3]["detail"] == "blocked"
