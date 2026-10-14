"""SetDeliveryModel over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.set_target_selection import (
    SetTargetSelectionPort,
)
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.driver_agent import DriverAgent
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.reject_invalid_credential import (
    helper_reject_invalid_credential,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import refuse_foreign_seat


class SetDeliveryModel:
    def __init__(
        self,
        *,
        credentials: CredentialStore | None,
        driver: DriverAgent | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_set_target_selection: SetTargetSelectionPort,
        admission: OperationAdmission,
    ) -> None:
        self.credentials = credentials
        self.driver = driver
        self.cap_delivery_config = cap_delivery_config
        self.cap_set_target_selection = cap_set_target_selection
        self.admission = admission

    def _execute(
        self,
        repo: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        timeout_seconds: int | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Persist a target's model directly (not via a named agent): the non-secret selection
        to the Console-local setting with the agent cleared (a direct set is not a named agent;
        R51), and the credential (if given) into the per-slug Secret. Writes NO git (R72), so a
        maintenance-only repo never gains a .delivery/ from model configuration. ``timeout_seconds``
        (when given) sets the worker's wall-clock budget in the same write; None preserves it.
        The credential is validated (issue #30) before it is seated: an explicit 401/403 raises,
        so the green tick means the worker will actually authenticate, not merely that a secret
        exists."""
        if credential:
            partial(helper_reject_invalid_credential, driver=self.driver)(
                credential, model, base_url
            )
        self.cap_set_target_selection.execute(
            repo,
            "",
            provider,
            base_url,
            model,
            timeout_seconds,
            seat={} if credential else None,
            context=context,
            operation_id=operation_id + "/set_target_selection",
            expected_revision=expected_revision,
        )
        if credential and self.credentials is not None:
            self.credentials.put_delivery(partial(helper_slug)(repo), credential)
        return self.cap_delivery_config.execute(repo)

    def execute(
        self,
        repo: str,
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        timeout_seconds: int | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.delivery_model", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                provider=provider,
                base_url=base_url,
                model=model,
                credential=credential,
                timeout_seconds=timeout_seconds,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.delivery_model",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "provider": provider,
                    "base_url": base_url,
                    "model": model,
                    "credential": credential,
                    "timeout_seconds": timeout_seconds,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(credential),
            validate=lambda: self._validate(
                repo=repo,
                provider=provider,
                base_url=base_url,
                model=model,
                credential=credential,
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
        provider: str,
        base_url: str,
        model: str,
        credential: str | None,
        timeout_seconds: int | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Persist a target's model directly (not via a named agent): the non-secret selection
        to the Console-local setting with the agent cleared (a direct set is not a named agent;
        R51), and the credential (if given) into the per-slug Secret. Writes NO git (R72), so a
        maintenance-only repo never gains a .delivery/ from model configuration. ``timeout_seconds``
        (when given) sets the worker's wall-clock budget in the same write; None preserves it.
        The credential is validated (issue #30) before it is seated: an explicit 401/403 raises,
        so the green tick means the worker will actually authenticate, not merely that a secret
        exists. A set that keeps the seated key points that key at a new endpoint and model,
        so on a personal seat it is its owner's alone."""
        if not credential:
            refuse_foreign_seat(self.cap_delivery_config.execute(repo), context)
        if credential:
            partial(helper_reject_invalid_credential, driver=self.driver)(
                credential, model, base_url
            )
