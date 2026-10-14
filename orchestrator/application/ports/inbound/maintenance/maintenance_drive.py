"""MaintenanceDrive application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.maintenance_drive_result import MaintenanceDriveResult
from orchestrator.domain.model.run_config import RunConfig


@runtime_checkable
class MaintenanceDrivePort(Protocol):
    def execute(
        self,
        repo: str,
        act: str,
        target: int | None,
        mode: str | None,
        config: RunConfig,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> MaintenanceDriveResult: ...
