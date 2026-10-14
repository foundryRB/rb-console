from delivery_fixtures import record_header, record_inputs
import pytest
from orchestrator.domain.services.delivery_resolution import gate_status, derive_from_records
from orchestrator.adapters.outbound.records.yaml_record_parser import parse
from orchestrator.domain.delivery import AWAITING_GATE, DEGRADED
from orchestrator.adapters.outbound.github.github_repo_store import _pending_gate

@pytest.mark.parametrize("signed", ["20261005", "2026-W41-1", "2026-02-30", "2026-10-05T00:00:00Z", "pending", "true", "2026-1-5"])
def test_gate_requires_exact_calendar_date(signed):
    text = f"---\nstatus: complete\ngate: proposal\nsigned: '{signed}'\n---\nProposal accepted: 2026-10-05\n"
    assert gate_status(record_header(text), "proposal") is None
    assert not parse(text).signed

@pytest.mark.parametrize("text", ["Proposal accepted: 2026-10-05", "---\nstatus: complete\ngate: design\nsigned: 2026-10-05\n---\n", "---\nstatus: in-progress\ngate: proposal\nsigned: 2026-10-05\n---\n"])
def test_prose_wrong_gate_and_incomplete_record_cannot_sign(text):
    assert gate_status(record_header(text), "proposal") is None

def test_signed_gate_uses_frontmatter_only():
    text = "---\nstatus: complete\ngate: proposal\nsigned: 2026-10-05\n---\nProposal accepted: PENDING\n"
    assert gate_status(record_header(text), "proposal") == "2026-10-05"

def test_wrong_gate_does_not_advance_phase():
    text = "---\nstatus: complete\ngate: design\nsigned: 2026-10-05\n---\n"
    state = derive_from_records("org/app", True, record_inputs({"proposal.md": text}))
    assert state.status == AWAITING_GATE
    assert state.blocked_gate == "proposal"

def test_record_without_canonical_frontmatter_is_degraded():
    state = derive_from_records("org/app", True, record_inputs({"proposal.md": "Proposal accepted: 2026-10-05"}))
    assert state.status == DEGRADED

def test_reopen_changes_canonical_signature_preserving_body():
    body = "Proposal accepted: 2026-10-05\nA historical quotation.\n"
    text = "---\nstatus: complete\ngate: proposal\nsigned: 2026-10-05\n---\n" + body
    result = _pending_gate(text)
    assert gate_status(record_header(result), "proposal") is None
    assert result.endswith(body)
    with pytest.raises(ValueError):
        _pending_gate(body)
