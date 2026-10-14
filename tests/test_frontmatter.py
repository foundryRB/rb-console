"""The frontmatter reader: a flat leading block, tolerant of records without one."""
from pytest_intent import intent

from orchestrator.adapters.outbound.records.yaml_record_parser import parse


@intent("INT-FC-R22")
def test_parse_reads_a_block_and_tolerates_its_absence():
    assert parse("no frontmatter here\njust prose") is None
    fm = parse(
        "---\n"
        "status: complete\n"
        "phase: scope\n"
        "gate: proposal\n"
        "signed: 2026-07-08\n"
        "attempt: 2\n"
        "mode: one-shot\n"
        "---\n"
        "# Proposal\n"
    )
    assert fm is not None
    assert fm.status == "complete"
    assert fm.signed is True
    assert fm.attempt == 2
    assert fm.mode == "one-shot"
    # a pending stamp is not a signature
    pending = parse("---\nstatus: complete\nsigned: pending\n---\n")
    assert pending is not None and pending.signed is False
