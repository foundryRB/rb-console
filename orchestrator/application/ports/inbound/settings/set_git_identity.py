"""SetGitIdentity application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class SetGitIdentityPort(Protocol):
    def execute(
        self,
        name: str,
        email: str,
        login: str,
        token: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict: ...
