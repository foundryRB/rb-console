"""The packaged worker helper imports the shared canonical record reader."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pytest_intent import intent


@intent('INT-FC-R20')
@pytest.mark.parametrize('text, expected', [('---\nstatus: complete\n---\n', 'complete'), ('---\nstatus: gate\n---\n', 'gate'), ('---\nstatus: aborted\n---\n', 'aborted'), ('---\nstatus: in-progress\n---\n', 'in-progress'), ('status: complete\n', None), ('---\nstatus: complete\nbroken: [\n---\n', None), ('---\nother: value\n---\nstatus: complete\n', None)])
def test_packaged_status_reader_requires_valid_leading_yaml(tmp_path, text, expected):
    root = Path(__file__).resolve().parents[1]
    image = tmp_path / 'image'
    image.mkdir()
    shutil.copyfile(root / 'devops/record_run.py', image / 'record_run.py')
    for relative in ['orchestrator/adapters/outbound/records/yaml_record_parser.py', 'orchestrator/domain/model/frontmatter.py', 'orchestrator/domain/model/record_status.py', 'orchestrator/domain/model/delivery_record.py']:
        target = image / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    record = tmp_path / 'record.md'
    record.write_text(text, encoding='utf-8')
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, str(image / 'record_run.py'), '--record-status', str(record)], cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == (1 if expected is None else 0)
    assert result.stdout.strip() == (expected or '')


@intent('INT-FC-R20')
def test_domain_consumes_normalized_records_and_a_durable_state_restores_as_values():
    from orchestrator.adapters.outbound.records.yaml_record_parser import parse_record
    from orchestrator.application.services.operations.command_payload import safe_value
    from orchestrator.application.services.operations.restore_result import (
        restore_result,
    )
    from orchestrator.domain.model.delivery_state import DeliveryState
    from orchestrator.domain.model.gate_state import GateState
    from orchestrator.domain.services.delivery_resolution import derive_from_records
    decoded = parse_record('---\nstatus: complete\ngate: proposal\nsigned: pending\nrun_cost: 1.25\nrun_turns: 2\nrun_model_a_tokens: 9\n---\n')
    state = derive_from_records('org/app', True, {'proposal.md': decoded})
    restored = restore_result(safe_value(state), DeliveryState)
    assert isinstance(restored.gates[0], GateState)
    assert restored == state
