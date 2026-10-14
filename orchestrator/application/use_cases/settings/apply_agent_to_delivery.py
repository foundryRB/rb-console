"""ApplyAgentToDelivery over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.set_target_selection import (
    SetTargetSelectionPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.agent import (
    helper_agent,
    helper_refuse_unusable_agent,
    helper_seat,
)
from orchestrator.domain.model.command_context import CommandContext


class ApplyAgentToDelivery:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        credentials: CredentialStore | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_set_target_selection: SetTargetSelectionPort,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.cap_delivery_config = cap_delivery_config
        self.cap_set_target_selection = cap_set_target_selection
        self.admission = admission

    def _execute(
        self,
        repo: str,
        name: str,
        model: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Point a target's model at a saved agent: copy the agent's credential into the per-slug
        Secret and record {agent, model} in the Console-local selection. Writes NO git (R72), so
        this works the same for a delivery and a maintenance-only repo (never fabricating a
        .delivery/). The model is chosen SEPARATELY (R73): the agent's default unless one is given."""
        fields, credential = partial(helper_agent, config=self.config)(name)
        partial(helper_refuse_unusable_agent)(name, fields, context)
        if not credential:
            raise ValueError(f"agent {name!r} has no credential")
        chosen = model if model else fields.get("model", "")
        self.cap_set_target_selection.execute(
            repo,
            name,
            fields.get("provider", "claude"),
            fields.get("base_url", ""),
            chosen,
            seat=partial(helper_seat)(fields),
            context=context,
            operation_id=operation_id + "/set_target_selection",
            expected_revision=expected_revision,
        )
        if self.credentials is not None:
            self.credentials.put_delivery(partial(helper_slug)(repo), credential)
        return self.cap_delivery_config.execute(repo)

    def execute(
        self,
        repo: str,
        name: str,
        model: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.apply_delivery", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                name=name,
                model=model,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.apply_delivery",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "name": name,
                    "model": model,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                name=name,
                model=model,
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
        name: str,
        model: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Point a target's model at a saved agent: copy the agent's credential into the per-slug
        Secret and record {agent, model} in the Console-local selection. Writes NO git (R72), so
        this works the same for a delivery and a maintenance-only repo (never fabricating a
        .delivery/). The model is chosen SEPARATELY (R73): the agent's default unless one is given."""
        fields, credential = partial(helper_agent, config=self.config)(name)
        partial(helper_refuse_unusable_agent)(name, fields, context)
        if not credential:
            raise ValueError(f"agent {name!r} has no credential")
        model if model else fields.get("model", "")
