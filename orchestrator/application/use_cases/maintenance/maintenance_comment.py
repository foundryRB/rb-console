"""MaintenanceComment over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.ports.outbound.maintenance_acts import MaintenanceActs
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.comment_created import CommentCreated


class MaintenanceComment:
    def __init__(
        self, *, macts: MaintenanceActs | None, admission: OperationAdmission
    ) -> None:
        self.macts = macts
        self.admission = admission

    def _execute(
        self,
        repo: str,
        number: int,
        body: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> CommentCreated:
        """The operator's comment, under fc-git, as gh would post it (INT-FC-R61)."""
        if self.macts is None:
            raise RuntimeError("no maintenance acts adapter is wired")
        if not (body or "").strip():
            raise ValueError("an empty comment is not a comment")
        return self.macts.comment(repo, number, body.strip())

    def execute(
        self,
        repo: str,
        number: int,
        body: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> CommentCreated:
        context.authorize("maintenance.comment", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                number=number,
                body=body,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "maintenance.comment",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "number": number,
                    "body": body,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                number=number,
                body=body,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            ),
        )
        if result:
            return result[0]
        return restore_result(
            retained, get_type_hints(self._execute).get("return", object)
        )

    def _validate(
        self,
        repo: str,
        number: int,
        body: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """The operator's comment, under fc-git, as gh would post it (INT-FC-R61)."""
        if self.macts is None:
            raise RuntimeError("no maintenance acts adapter is wired")
        if not (body or "").strip():
            raise ValueError("an empty comment is not a comment")
