"""SetDriverConfig application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.driver_config import DriverConfig


@runtime_checkable
class SetDriverConfigPort(Protocol):
    def execute(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig: ...
