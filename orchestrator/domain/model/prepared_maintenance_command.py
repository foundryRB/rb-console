"""PreparedMaintenanceCommand semantic maintenance value."""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.maintenance_command_evidence import (
    MaintenanceCommandEvidence,
)
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.run_config import RunConfig


@dataclass(frozen=True)
class PreparedMaintenanceCommand:
    workflow: CompiledWorkflow
    config: RunConfig
    run_id: str
    repository: str
    act: str
    target: int | None
    mode: MaintenanceMode
    context: CommandContext
    evidence: MaintenanceCommandEvidence
