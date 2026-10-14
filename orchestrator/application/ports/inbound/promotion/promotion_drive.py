"""PromotionDrive application capability."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.promotion_drive_result import PromotionDriveResult


@runtime_checkable
class PromotionDrivePort(Protocol):

    def execute(self, repo: str, target_name: str, release: str='', *, context: CommandContext, operation_id: str, expected_revision: str | None=None) -> PromotionDriveResult:
        ...
