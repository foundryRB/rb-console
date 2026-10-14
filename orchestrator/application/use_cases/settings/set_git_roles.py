"""SetGitRoles over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _GIT_ROLES
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.drop_console_credential import (
    helper_drop_console_credential,
)
from orchestrator.application.services.settings.git_role_keys import (
    helper_git_role_keys,
)
from orchestrator.application.services.settings.held_credential import HeldCredential
from orchestrator.domain.model.command_context import CommandContext


class SetGitRoles:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        console_credential: HeldCredential | None,
        cap_git_roles: GitRolesPort,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.console_credential = console_credential
        self.cap_git_roles = cap_git_roles
        self.admission = admission

    def _execute(
        self,
        roles: dict,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Persist the role -> identity map. Unknown role keys are dropped and an empty value
        clears a role to unassigned - no identity (INT-FC-R90)."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        valid = set(partial(helper_git_role_keys)())
        clean = {
            k: str(v)
            for k, v in (roles or {}).items()
            if k in valid and str(v or "").strip()
        }
        self.config.put_setting(_GIT_ROLES, clean, None)
        partial(
            helper_drop_console_credential, console_credential=self.console_credential
        )()
        return self.cap_git_roles.execute()

    def execute(
        self,
        roles: dict,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.git_roles", "")
        result = []

        def dispatch():
            value = self._execute(
                roles=roles,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.git_roles",
            "",
            operation_id,
            safe_value({"roles": roles, "expected_revision": expected_revision}),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                roles=roles,
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
        roles: dict,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Persist the role -> identity map. Unknown role keys are dropped and an empty value
        clears a role to unassigned - no identity (INT-FC-R90)."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        valid = set(partial(helper_git_role_keys)())
        {
            k: str(v)
            for k, v in (roles or {}).items()
            if k in valid and str(v or "").strip()
        }
