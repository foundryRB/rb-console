"""SetPairCredential application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class SetPairCredentialPort(Protocol):
    def execute(
        self,
        name: str,
        host: str = "",
        login: str = "",
        token: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict: ...
