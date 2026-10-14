from delivery_fixtures import record_header
"""Tests for the deterministic state resolver: the orchestrator's heart.

These assert the derivation rules: progress comes from which committed records
exist and whether each gate is signed. They also assert the resolver is
read-only (Principle 4: the Console owns nothing and writes no delivery artifact).
Each test attests one intent claim (INT-FC-Rnn); audit with `csd-intent .`.
"""
from pytest_intent import intent

from orchestrator.domain.services.delivery_resolution import gate_status
from orchestrator.adapters.outbound.filesystem.local_delivery_reader import derive_state
from orchestrator.domain.delivery import (
    AWAITING_GATE,
    DEGRADED,
    DELIVERED,
    LEARNED,
    NOT_A_DELIVERY,
    RUN_PHASE,
)


def _scratch(tmp_path):
    d = tmp_path / ".delivery"
    d.mkdir()
    return d


def _sign(scratch, record, stamp):
    from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
    phase = next(phase for phase in CURRENT_LIFECYCLE.phases if phase.record == record)
    signed = stamp.rsplit(": ", 1)[-1]
    (scratch / record).write_text(f"---\nphase: {phase.name}\nstatus: complete\ngate: {phase.gate}\nsigned: {signed}\n---\n", encoding="utf-8")


@intent("INT-FC-R01")
def test_absent_delivery_is_not_a_delivery(tmp_path):
    state = derive_state(tmp_path)
    assert state.status == NOT_A_DELIVERY
    assert state.exists is False
    assert "deliver-engagement" in state.next_command


@intent("INT-FC-R02")
def test_empty_scratch_runs_scope(tmp_path):
    _scratch(tmp_path)
    state = derive_state(tmp_path)
    assert state.status == RUN_PHASE
    assert state.phase == "scope"
    assert state.next_skill == "deliver-engagement"


@intent("INT-FC-R03")
def test_signed_proposal_advances_to_design(tmp_path):
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    state = derive_state(tmp_path)
    assert state.status == RUN_PHASE
    assert state.phase == "design"
    assert state.next_skill == "design-session"
    assert state.gates[0].signed


@intent("INT-FC-R04")
def test_pending_gate_suspends(tmp_path):
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: PENDING")
    state = derive_state(tmp_path)
    assert state.status == AWAITING_GATE
    assert state.blocked_gate == "proposal"
    assert "sign" in state.next_command


@intent("INT-FC-R05")
def test_all_signed_is_ready_to_reconcile(tmp_path):
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    _sign(scratch, "design.md", "Design approved: 2026-07-01")
    _sign(scratch, "handoff.md", "Plan signed: 2026-07-03")
    _sign(scratch, "build.md", "Delivery accepted: 2026-07-07")
    state = derive_state(tmp_path)
    assert state.status == DELIVERED
    assert state.next_skill == "reconcile-delivery"
    assert all(gate.signed for gate in state.gates)
    assert len(state.gates) == 4


def _sign_all(scratch):
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    _sign(scratch, "design.md", "Design approved: 2026-07-01")
    _sign(scratch, "handoff.md", "Plan signed: 2026-07-03")
    _sign(scratch, "build.md", "Delivery accepted: 2026-07-07")


@intent("INT-FC-R106")
def test_learned_journal_resolves_learned(tmp_path):
    # All four gates signed AND the journal frontmatter carries Learn's stamp:
    # Learn demonstrably ran, so the next act is the deliberate close, not a re-drive.
    scratch = _scratch(tmp_path)
    _sign_all(scratch)
    (scratch / "journal.md").write_text(
        "---\nlearned: 2026-07-25\n---\n# Delivery journal\n\nlessons...\n",
        encoding="utf-8",
    )
    state = derive_state(tmp_path)
    assert state.status == LEARNED
    assert state.phase == "learn"
    assert state.learned_on == "2026-07-25"
    assert state.next_skill is None
    assert "close" in state.next_command


@intent("INT-FC-R106")
def test_journal_without_stamp_stays_delivered(tmp_path):
    # A journal with no leading frontmatter (or a non-date learned:) is not proof
    # Learn ran; the line keeps routing to reconcile-delivery.
    scratch = _scratch(tmp_path)
    _sign_all(scratch)
    (scratch / "journal.md").write_text("# Delivery journal\n\nentries...\n", encoding="utf-8")
    assert derive_state(tmp_path).status == DELIVERED
    (scratch / "journal.md").write_text(
        "---\nlearned: pending\n---\n# Delivery journal\n", encoding="utf-8"
    )
    assert derive_state(tmp_path).status == DELIVERED


@intent("INT-FC-R106")
def test_learned_stamp_ignored_while_gates_open(tmp_path):
    # The stamp only reads once every gate is signed; mid-line it changes nothing
    # (the derived pointer wins over a stray or stale stamp).
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    (scratch / "journal.md").write_text(
        "---\nlearned: 2026-07-25\n---\n# Delivery journal\n", encoding="utf-8"
    )
    state = derive_state(tmp_path)
    assert state.status == RUN_PHASE
    assert state.phase == "design"
    assert state.learned_on is None


@intent("INT-FC-R06")
def test_resume_mid_line_from_records_alone(tmp_path):
    # proposal + design signed, handoff missing -> resume at intent+plan.
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    _sign(scratch, "design.md", "Design approved: 2026-07-01")
    state = derive_state(tmp_path)
    assert state.status == RUN_PHASE
    assert state.phase == "intent+plan"
    assert state.next_skill == "intent-session"


@intent("INT-FC-R07")
def test_derivation_is_read_only(tmp_path):
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    before = sorted(p.name for p in scratch.iterdir())
    derive_state(tmp_path)
    derive_state(tmp_path)  # idempotent
    after = sorted(p.name for p in scratch.iterdir())
    assert before == after


@intent("INT-FC-R08")
def test_gate_status_parsing():
    assert gate_status(record_header("---\nstatus: complete\ngate: proposal\nsigned: 2026-06-28\n---\n"), "proposal") == "2026-06-28"
    assert gate_status(record_header("---\nstatus: complete\ngate: design\nsigned: pending\n---\n"), "design") is None
    assert gate_status(record_header("nothing to see here"), "proposal") is None


@intent("INT-FC-R74")
def test_aborted_record_resolves_degraded(tmp_path):
    # A degraded stop stamps status: aborted in the record frontmatter and leaves the
    # gate unsigned. The cockpit must surface DEGRADED, not "done, awaiting gate" -
    # reading the status the worker wrote, not only the gate date.
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    _sign(scratch, "design.md", "Design approved: 2026-07-01")
    _sign(scratch, "handoff.md", "Plan signed: 2026-07-03")
    (scratch / "build.md").write_text(
        "---\nphase: build\nstatus: aborted\ngate: delivery\nsigned: pending\n---\n\nCI never went green.\n",
        encoding="utf-8",
    )
    state = derive_state(tmp_path)
    assert state.status == DEGRADED
    assert state.phase == "build+ship"
    assert "re-drive" in state.next_command


@intent("INT-FC-R74")
def test_complete_record_still_advances(tmp_path):
    # The guard must not regress a healthy record: status: complete with a signed
    # gate advances exactly as before.
    scratch = _scratch(tmp_path)
    _sign(scratch, "proposal.md", "Proposal accepted: 2026-06-28")
    _sign(scratch, "design.md", "Design approved: 2026-07-01")
    _sign(scratch, "handoff.md", "Plan signed: 2026-07-03")
    (scratch / "build.md").write_text(
        "---\nphase: build\nstatus: complete\ngate: delivery\nsigned: 2026-07-07\n---\n\nShipped.\n",
        encoding="utf-8",
    )
    state = derive_state(tmp_path)
    assert state.status == DELIVERED
