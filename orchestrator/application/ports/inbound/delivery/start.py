"""Start application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery.next_action import NextAction
from orchestrator.domain.model.run_config import RunConfig


@runtime_checkable
class StartPort(Protocol):
    def execute(
        self,
        target: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction: ...
