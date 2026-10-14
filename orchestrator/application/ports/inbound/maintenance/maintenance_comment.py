"""MaintenanceComment application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.comment_created import CommentCreated


@runtime_checkable
class MaintenanceCommentPort(Protocol):
    def execute(
        self,
        repo: str,
        number: int,
        body: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> CommentCreated: ...
