"""Derive a delivery's state from its committed ``.delivery/`` records.

Pure and read-only. ``derive_from_records`` is the heart: given which records exist
and their normalized facts, it returns a :class:`DeliveryState` (GitOps-style, no status field).
``derive_state`` reads the records from the local filesystem and calls it; a remote
source (GitHub) fetches them over the API and calls the same pure function, so the
two paths cannot diverge.
"""
from __future__ import annotations

from collections.abc import Mapping

from orchestrator.domain.current_lifecycle import CURRENT_LIFECYCLE
from orchestrator.domain.delivery import (
    AWAITING_GATE,
    DEGRADED,
    DELIVERED,
    LEARNED,
    NOT_A_DELIVERY,
    RUN_PHASE,
)
from orchestrator.domain.model.delivery_record import DeliveryRecord
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.frontmatter import Frontmatter
from orchestrator.domain.model.gate_state import GateState
from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition
from orchestrator.domain.model.record_status import RecordStatus


def gate_status(frontmatter: Frontmatter | None, gate: str) -> str | None:
    """Read the signature of this exact gate from canonical frontmatter."""
    if not gate or frontmatter is None or frontmatter.gate != gate or frontmatter.status not in (RecordStatus.COMPLETE, RecordStatus.GATE):
        return None
    return frontmatter.signed_on or None


def _not_a_delivery(repo: str, definition: LifecycleDefinition = CURRENT_LIFECYCLE) -> DeliveryState:
    return DeliveryState(
        repo=repo,
        exists=False,
        status=NOT_A_DELIVERY,
        phase=None,
        next_skill="deliver-engagement",
        next_command=f"deliver-engagement {repo} <request>",
        blocked_gate=None,
        gates=(),
        records_present=(),
        lifecycle=definition,
    )


def derive_from_records(repo: str, exists: bool, contents: Mapping[str, DeliveryRecord], definition: LifecycleDefinition = CURRENT_LIFECYCLE) -> DeliveryState:
    """Resolve records through the line's effective phase definition."""
    if not exists:
        return _not_a_delivery(repo, definition)
    records_on_disk = tuple(p.record for p in definition.phases if p.record in contents)
    reviewed_records = tuple(name for name, record in contents.items() if record.frontmatter is not None and record.frontmatter.reviewed)
    gates: list[GateState] = []
    present: list[str] = []
    learned_on = ""
    for phase in definition.phases:
        record = contents.get(phase.record)
        fm = record.frontmatter if record is not None else None
        if phase.completion == "journal":
            if fm is None or not fm.learned:
                return DeliveryState(repo, True, DELIVERED, phase.name, phase.skill, f"{phase.skill} {repo}", None, tuple(gates), tuple(present), lifecycle=definition, records_on_disk=records_on_disk, reviewed_records=reviewed_records)
            learned_on = fm.learned
            continue
        if phase.record not in contents:
            return DeliveryState(repo, True, RUN_PHASE, phase.name, phase.skill, f"{phase.skill} {repo}", None, tuple(gates), tuple(present), lifecycle=definition, records_on_disk=records_on_disk, reviewed_records=reviewed_records)
        present.append(phase.record)
        if fm is None or fm.status not in (RecordStatus.COMPLETE, RecordStatus.GATE):
            return DeliveryState(repo, True, DEGRADED, phase.name, phase.skill, f"clear the blocker, then re-drive the {phase.name} phase", None, tuple(gates), tuple(present), lifecycle=definition, records_on_disk=records_on_disk, reviewed_records=reviewed_records)
        if phase.gate:
            signed = gate_status(fm, phase.gate)
            gates.append(GateState(phase.gate, signed))
            if signed is None:
                # A gate whose one-shot stamp refused names the refusal, so the operator reads
                # why the line stopped where they sign it (#181).
                refused = f" (the one-shot stamp refused: {fm.stamp_refused})" if fm.stamp_refused else ""
                return DeliveryState(repo, True, AWAITING_GATE, phase.name, None, f"sign the {phase.gate} gate{refused}", phase.gate, tuple(gates), tuple(present), lifecycle=definition, records_on_disk=records_on_disk, reviewed_records=reviewed_records)
        elif fm is None or fm.status != RecordStatus.COMPLETE:
            return DeliveryState(repo, True, DEGRADED, phase.name, phase.skill, f"complete the {phase.name} record", None, tuple(gates), tuple(present), lifecycle=definition, records_on_disk=records_on_disk, reviewed_records=reviewed_records)
    final = definition.phases[-1]
    return DeliveryState(repo, True, LEARNED, final.name, None, "close the line (tag delivered/<slug>/P<n>, remove the scratch ref)", None, tuple(gates), tuple(present), learned_on=learned_on, lifecycle=definition, records_on_disk=records_on_disk, reviewed_records=reviewed_records)
