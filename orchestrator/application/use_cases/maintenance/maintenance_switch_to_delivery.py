"""MaintenanceSwitchToDelivery over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.maintenance_resolver import delivery_prompt_of
from orchestrator.application.ports.outbound.maintenance_acts import MaintenanceActs
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext


class MaintenanceSwitchToDelivery:
    def __init__(
        self,
        *,
        macts: MaintenanceActs | None,
        msource: MaintenanceSource | None,
        admission: OperationAdmission,
    ) -> None:
        self.macts = macts
        self.msource = msource
        self.admission = admission

    def _execute(
        self,
        repo: str,
        number: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Switch an over-scope maintenance ticket to a delivery line (INT-FC-R100, issue #13).
        The ticket carries the foundry-delivery-scale label and a prepared delivery brief: the
        marked comment the resolve worker left when it parked its run delivery-scale (worker
        exit 65), or the ticket's own body when the ticket was authored as the brief itself and
        no comment carries the marker. This is the operator pressing "Switch to Delivery": it
        reads that brief back off the ticket (so the Delivery view's "Open a delivery line" form
        can be pre-filled with it) and hides the ticket from the maintenance pane by adding the
        foundry-hidden label - the #12 mirror, so the concern reads once, now as a delivery line
        rather than a backlog ticket. Nothing here opens the line: the operator does that through
        the existing deterministic establish action, with the prompt already in the form.

        The prompt is read BEFORE the label write, so a read that degrades to "" (an unreachable
        API) still lets the hide proceed; the write refuses loudly without a git credential, the
        same fail-closed rule every other maintenance act follows (INT-FC-R61)."""
        if self.macts is None or self.msource is None:
            raise RuntimeError("no maintenance acts/source adapter is wired")
        prompt = delivery_prompt_of(
            self.msource.issue_comments(repo, number),
            self.msource.issue(repo, number).body,
        )
        self.macts.label(repo, number, "foundry-hidden")
        return {"prompt": prompt, "hidden": True}

    def execute(
        self,
        repo: str,
        number: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("maintenance.switch_to_delivery", repo)
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
            "maintenance.switch_to_delivery",
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
        """Switch an over-scope maintenance ticket to a delivery line (INT-FC-R100, issue #13).
        The ticket carries the foundry-delivery-scale label and a prepared delivery brief: the
        marked comment the resolve worker left when it parked its run delivery-scale (worker
        exit 65), or the ticket's own body when the ticket was authored as the brief itself and
        no comment carries the marker. This is the operator pressing "Switch to Delivery": it
        reads that brief back off the ticket (so the Delivery view's "Open a delivery line" form
        can be pre-filled with it) and hides the ticket from the maintenance pane by adding the
        foundry-hidden label - the #12 mirror, so the concern reads once, now as a delivery line
        rather than a backlog ticket. Nothing here opens the line: the operator does that through
        the existing deterministic establish action, with the prompt already in the form.

        The prompt is read BEFORE the label write, so a read that degrades to "" (an unreachable
        API) still lets the hide proceed; the write refuses loudly without a git credential, the
        same fail-closed rule every other maintenance act follows (INT-FC-R61)."""
        if self.macts is None or self.msource is None:
            raise RuntimeError("no maintenance acts/source adapter is wired")
        delivery_prompt_of(
            self.msource.issue_comments(repo, number),
            self.msource.issue(repo, number).body,
        )
