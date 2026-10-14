"""SetGitIdentity over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.git_credential_check import (
    GitCredentialCheck,
)
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
from orchestrator.application.services.settings.reject_invalid_git_token import (
    helper_reject_invalid_git_token,
)
from orchestrator.domain.model.command_context import CommandContext


class SetGitIdentity:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        console_credential: HeldCredential | None,
        gitcheck: GitCredentialCheck | None,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.console_credential = console_credential
        self.gitcheck = gitcheck
        self.admission = admission

    def _execute(
        self,
        name: str,
        email: str,
        login: str,
        token: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Save (or update) a named git identity. The PAT is stored in its own Secret; an empty
        one keeps the stored value, so editing the email/login doesn't require re-entering it.
        ``login`` is the GitHub username the maintenance derivation matches on; ``name``/``email``
        are the commit author the worker stamps. A supplied token is validated against the repo
        host before it is seated (INT-FC-R142), so the pane's tick means the worker will actually
        authenticate rather than merely that a Secret exists."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        slug = partial(helper_agent_slug)(name)
        if not slug:
            raise ValueError("a git identity needs a name")
        fields = {"name": name, "email": email or "", "login": login or ""}
        if token:
            partial(helper_reject_invalid_git_token, gitcheck=self.gitcheck)(
                token, login or ""
            )
        saved = self.config.put_setting(_GITID + slug, fields, token)
        partial(
            helper_drop_console_credential, console_credential=self.console_credential
        )()
        return saved

    def execute(
        self,
        name: str,
        email: str,
        login: str,
        token: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.git_identity", "")
        result = []

        def dispatch():
            value = self._execute(
                name=name,
                email=email,
                login=login,
                token=token,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.git_identity",
            "",
            operation_id,
            safe_value(
                {
                    "name": name,
                    "email": email,
                    "login": login,
                    "token": token,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(token),
            validate=lambda: self._validate(
                name=name,
                email=email,
                login=login,
                token=token,
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
        email: str,
        login: str,
        token: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Save (or update) a named git identity. The PAT is stored in its own Secret; an empty
        one keeps the stored value, so editing the email/login doesn't require re-entering it.
        ``login`` is the GitHub username the maintenance derivation matches on; ``name``/``email``
        are the commit author the worker stamps. A supplied token is validated against the repo
        host before it is seated (INT-FC-R142), so the pane's tick means the worker will actually
        authenticate rather than merely that a Secret exists."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        slug = partial(helper_agent_slug)(name)
        if not slug:
            raise ValueError("a git identity needs a name")
        if token:
            partial(helper_reject_invalid_git_token, gitcheck=self.gitcheck)(
                token, login or ""
            )
