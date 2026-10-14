"""Validated, immutable phase order and completion contracts."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.lifecycle_artifacts import SUPPORTED_ARTIFACTS
from orchestrator.domain.model.phase import Phase


@dataclass(frozen=True)
class LifecycleDefinition:
    id: str
    version: str
    phases: tuple[Phase, ...]
    schema_version: int = 1
    source_ref: str = ""
    worker_image: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1 or not self.id or not self.version or not self.phases:
            raise ValueError("invalid lifecycle identity or schema")
        seen: set[str] = set()
        records: set[str] = set()
        gates: set[str] = set()
        for phase in self.phases:
            if phase.artifact not in SUPPORTED_ARTIFACTS:
                raise ValueError("unsupported phase artifact")
            if not phase.name or phase.name in seen or phase.completion not in {"record", "journal"}:
                raise ValueError("duplicate phase or unsupported completion")
            if any(item not in seen for item in phase.inputs) or len(set(phase.inputs)) != len(phase.inputs):
                raise ValueError("phase dependencies must name earlier phases")
            if not phase.tool or not phase.skill or not phase.agent or not phase.record or phase.record in records or "/" in phase.record or "\\" in phase.record:
                raise ValueError("invalid phase catalog reference or record")
            if phase.gate and phase.gate in gates:
                raise ValueError("duplicate phase gate")
            if phase.completion == "journal" and (phase.record != "journal.md" or phase.gate):
                raise ValueError("journal handler requires an ungated journal")
            seen.add(phase.name)
            records.add(phase.record)
            if phase.gate:
                gates.add(phase.gate)
