"""MaintenanceCommandEvidence semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaintenanceCommandEvidence:
    source_revision: str
    contract_revision: str
    repository_id: str
    run_id: str
