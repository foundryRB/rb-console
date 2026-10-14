"""Advance over consumed application contracts."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.delivery.plan_next import PlanNextPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.outbound.worker_runner import WorkerRunner
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.with_delivery_config import (
    helper_with_delivery_config,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery.next_action import NextAction
from orchestrator.domain.model.run_config import RunConfig


class Advance:
    def __init__(
        self,
        *,
        runner: WorkerRunner | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_plan_next: PlanNextPort,
        admission: OperationAdmission,
    ) -> None:
        self.runner = runner
        self.cap_delivery_config = cap_delivery_config
        self.cap_plan_next = cap_plan_next
        self.admission = admission

    def _execute(
        self,
        repo: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction:
        """Apply the admitted advance command using its prepared inputs."""
        config = partial(
            helper_with_delivery_config, cap_delivery_config=self.cap_delivery_config
        )(repo, config)
        action = self.cap_plan_next.execute(repo, config)
        if (
            action.kind == "launch"
            and action.launch is not None
            and (self.runner is not None)
        ):
            return replace(action, handle=self.runner.launch(action.launch))
        return action

    def execute(
        self,
        repo: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction:
        context.authorize("delivery.advance", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                config=config,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.advance",
            repo,
            operation_id,
            safe_value(
                {"repo": repo, "config": config, "expected_revision": expected_revision}
            ),
            dispatch,
            secret_write=bool(config.worker_credential),
            validate=lambda: self._validate(
                repo=repo,
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
        repo: str,
        config: RunConfig,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> NextAction:
        """Validate fresh advance preconditions before recording command intent."""
        config = partial(
            helper_with_delivery_config, cap_delivery_config=self.cap_delivery_config
        )(repo, config)
        self.cap_plan_next.execute(repo, config)
