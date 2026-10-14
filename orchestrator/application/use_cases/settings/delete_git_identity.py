"""DeleteGitIdentity over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _GITID
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.drop_console_credential import (
    helper_drop_console_credential,
)
from orchestrator.application.services.settings.held_credential import HeldCredential
from orchestrator.domain.model.command_context import CommandContext


class DeleteGitIdentity:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        console_credential: HeldCredential | None,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.console_credential = console_credential
        self.admission = admission

    def _execute(
        self,
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        if self.config is not None:
            self.config.delete_setting(_GITID + partial(helper_agent_slug)(name))
        partial(
            helper_drop_console_credential, console_credential=self.console_credential
        )()

    def execute(
        self,
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        context.authorize("settings.delete_git_identity", "")
        result = []

        def dispatch():
            value = self._execute(
                name=name,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.delete_git_identity",
            "",
            operation_id,
            safe_value({"name": name, "expected_revision": expected_revision}),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                name=name,
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
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        pass
