"""Delegated merges through the fresh-evidence command capability."""

from __future__ import annotations

from orchestrator.application.ports.inbound.maintenance.maintenance_merge import (
    MaintenanceMergePort,
)
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.comment_created import CommentCreated
from orchestrator.domain.model.issue_closed import IssueClosed
from orchestrator.domain.model.pull_merge_result import PullMergeResult


class AdmittedMaintenanceActs:
    def __init__(self, merge: MaintenanceMergePort, context: CommandContext) -> None:
        self.merge_port = merge
        self.context = context

    def merge(self, repo: str, number: int, *, expected_head: str = "") -> PullMergeResult:
        return self.merge_port.execute(
            repo,
            number,
            context=self.context,
            operation_id=f"reconcile:merge:{number}",
            expected_revision=expected_head or None,
        )

    def comment(self, repo: str, number: int, body: str) -> CommentCreated:
        raise PermissionDenied("The scheduler grant permits no comments")

    def close_issue(self, repo: str, number: int) -> IssueClosed:
        raise PermissionDenied("The scheduler grant permits no ticket closure")

    def label(self, repo: str, number: int, label: str) -> None:
        raise PermissionDenied("The scheduler grant permits no labels")
