"""Start over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.ports.inbound.delivery.establish import EstablishPort
from orchestrator.application.ports.inbound.delivery.plan_next import PlanNextPort
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery.next_action import NextAction
from orchestrator.domain.model.run_config import RunConfig


class Start:
    def __init__(
        self,
        *,
        cap_plan_next: PlanNextPort,
        admission: OperationAdmission,
        cap_establish: EstablishPort,
    ) -> None:
        self.cap_plan_next = cap_plan_next
        self.admission = admission
        self.cap_establish = cap_establish

    def _execute(
        self,
        target: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction:
        if not config.complete:
            raise ValueError(
                "config incomplete: missing " + ", ".join(config.missing())
            )
        state = self.cap_establish.execute(
            target,
            context=context,
            operation_id=operation_id + "/establish",
            expected_revision=expected_revision,
        )
        return self.cap_plan_next.execute(state.repo, config)

    def execute(
        self,
        target: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction:
        context.authorize("delivery.start", target)
        result = []

        def dispatch():
            value = self._execute(
                target=target,
                config=config,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.start",
            target,
            operation_id,
            safe_value(
                {
                    "target": target,
                    "config": config,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(config.worker_credential),
            validate=lambda: self._validate(
                target=target,
                config=config,
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
        target: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction:
        if not config.complete:
            raise ValueError(
                "config incomplete: missing " + ", ".join(config.missing())
            )
