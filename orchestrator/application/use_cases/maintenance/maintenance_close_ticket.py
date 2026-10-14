"""MaintenanceCloseTicket over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.events import TICKET_CLOSED, state_fact
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.maintenance_acts import MaintenanceActs
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.issue_closed import IssueClosed


class MaintenanceCloseTicket:
    def __init__(
        self,
        *,
        events: EventPublisher | None,
        macts: MaintenanceActs | None,
        admission: OperationAdmission,
    ) -> None:
        self.events = events
        self.macts = macts
        self.admission = admission

    def _execute(
        self,
        repo: str,
        number: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> IssueClosed:
        """Close a ticket whose PR merged but did not auto-close it (INT-FC-R86): byte-identical
        to gh issue close, under the shared identity. The lifecycle's last act when the merge
        keyword was missing from the PR body - the loop's own close, so the ticket leaves the
        backlog instead of lingering merged-but-open."""
        if self.macts is None:
            raise RuntimeError("no maintenance acts adapter is wired")
        closed = self.macts.close_issue(repo, number)
        state_fact(
            self.events,
            event_type=TICKET_CLOSED,
            subject=repo,
            data={"repo": repo, "ticket": number},
        )
        return closed

    def execute(
        self,
        repo: str,
        number: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> IssueClosed:
        context.authorize("maintenance.close", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                number=number,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "maintenance.close",
            repo,
            operation_id,
            safe_value(
                {"repo": repo, "number": number, "expected_revision": expected_revision}
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                number=number,
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
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Close a ticket whose PR merged but did not auto-close it (INT-FC-R86): byte-identical
        to gh issue close, under the shared identity. The lifecycle's last act when the merge
        keyword was missing from the PR body - the loop's own close, so the ticket leaves the
        backlog instead of lingering merged-but-open."""
        if self.macts is None:
            raise RuntimeError("no maintenance acts adapter is wired")
