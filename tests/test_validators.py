from delivery_fixtures import record_inputs

"""Record resolution uses the canonical leading YAML reader and explicit signatures."""
import pytest
from pytest_intent import intent

from orchestrator.adapters.outbound.records.yaml_record_parser import parse
from orchestrator.domain.delivery import AWAITING_GATE, DEGRADED
from orchestrator.domain.services.delivery_resolution import derive_from_records


@intent('INT-FC-R20')
@pytest.mark.parametrize('record', ['body only status: complete', 'status: complete\n', '---\nstatus: [complete\n---\n', '---\nstatus: unsupported\n---\n', '---\nstatus: in-progress\n---\n', ''])
def test_invalid_record_cannot_establish_phase_completion(record):
    state = derive_from_records('org/app', True, record_inputs({'proposal.md': record}))
    assert state.status == DEGRADED
    assert state.phase == 'scope'
    assert not state.gates or not state.gates[0].signed

@intent('INT-FC-R21')
@pytest.mark.parametrize('mode', ['interactive', 'one-shot'])
def test_unsigned_complete_record_requires_a_real_gate_signature_in_every_mode(mode):
    record = f'---\nstatus: complete\ngate: proposal\nsigned: pending\nmode: {mode}\n---\n'
    assert parse(record).signed is False
    state = derive_from_records('org/app', True, record_inputs({'proposal.md': record}))
    assert state.status == AWAITING_GATE and state.blocked_gate == 'proposal'
