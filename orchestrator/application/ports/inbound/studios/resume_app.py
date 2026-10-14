"""ResumeApp application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.app_lifecycle_result import AppLifecycleResult
from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class ResumeAppPort(Protocol):
    def execute(
        self,
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> AppLifecycleResult: ...
