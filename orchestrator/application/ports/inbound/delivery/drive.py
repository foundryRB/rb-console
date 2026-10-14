"""Drive application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery.drive_result import DriveResult
from orchestrator.domain.model.run_config import RunConfig


@runtime_checkable
class DrivePort(Protocol):
    def execute(
        self,
        repo: str,
        config: RunConfig,
        run_id: str,
        from_phase: str | None = None,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriveResult: ...
