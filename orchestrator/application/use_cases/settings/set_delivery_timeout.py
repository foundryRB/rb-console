"""SetDeliveryTimeout over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.set_target_selection import (
    SetTargetSelectionPort,
)
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext


class SetDeliveryTimeout:
    def __init__(
        self,
        *,
        cap_delivery_config: DeliveryConfigPort,
        cap_set_target_selection: SetTargetSelectionPort,
        admission: OperationAdmission,
    ) -> None:
        self.cap_delivery_config = cap_delivery_config
        self.cap_set_target_selection = cap_set_target_selection
        self.admission = admission

    def _execute(
        self,
        repo: str,
        timeout_seconds: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Set the delivery's worker wall-clock budget (seconds), preserving its model choice.
        A build+ship that needs hours is the delivery's call, not a flat constant; this is where
        the operator makes it, beside the model. Floored in set_target_selection (a 0 kills the pod)."""
        dc = self.cap_delivery_config.execute(repo)
        self.cap_set_target_selection.execute(
            repo,
            dc["agent"],
            dc["provider"],
            dc["base_url"],
            dc["model"],
            int(timeout_seconds),
            context=context,
            operation_id=operation_id + "/set_target_selection",
            expected_revision=expected_revision,
        )
        return self.cap_delivery_config.execute(repo)

    def execute(
        self,
        repo: str,
        timeout_seconds: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.delivery_timeout", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                timeout_seconds=timeout_seconds,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.delivery_timeout",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "timeout_seconds": timeout_seconds,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                timeout_seconds=timeout_seconds,
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
        timeout_seconds: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Set the delivery's worker wall-clock budget (seconds), preserving its model choice.
        A build+ship that needs hours is the delivery's call, not a flat constant; this is where
        the operator makes it, beside the model. Floored in set_target_selection (a 0 kills the pod)."""
        self.cap_delivery_config.execute(repo)
