"""SetPairCredential over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _DEFAULT_PAIR_HOST, _PAIR
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext


class SetPairCredential:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        cap_pair_credential_held: PairCredentialHeldPort,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.cap_pair_credential_held = cap_pair_credential_held
        self.admission = admission

    def _execute(
        self,
        name: str,
        host: str = "",
        login: str = "",
        token: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Register (or amend) a pair credential the platform holds for one pair.

        The secret is REQUIRED to register: a pair credential with no secret is the exact
        state issue #131 describes - a name that resolves to nothing - and admitting one
        would let the console report a door as openable that no act can open. Amending an
        already-held credential may omit it, so correcting a host or a login does not mean
        pasting the token again."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        slug = partial(helper_agent_slug)(name)
        if not slug:
            raise ValueError("a pair credential needs a name")
        if not token and (not self.cap_pair_credential_held.execute(name)):
            raise ValueError(
                f"registering {name} needs the secret the pair granted us; the platform mints no credential for a repository it does not own"
            )
        fields = {
            "name": name,
            "host": (host or "").strip() or _DEFAULT_PAIR_HOST,
            "login": (login or "").strip(),
        }
        return self.config.put_setting(_PAIR + slug, fields, token)

    def execute(
        self,
        name: str,
        host: str = "",
        login: str = "",
        token: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.pair_credential", "")
        result = []

        def dispatch():
            value = self._execute(
                name=name,
                host=host,
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
            "settings.pair_credential",
            "",
            operation_id,
            safe_value(
                {
                    "name": name,
                    "host": host,
                    "login": login,
                    "token": token,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(token),
            validate=lambda: self._validate(
                name=name,
                host=host,
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
        host: str = "",
        login: str = "",
        token: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Register (or amend) a pair credential the platform holds for one pair.

        The secret is REQUIRED to register: a pair credential with no secret is the exact
        state issue #131 describes - a name that resolves to nothing - and admitting one
        would let the console report a door as openable that no act can open. Amending an
        already-held credential may omit it, so correcting a host or a login does not mean
        pasting the token again."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        slug = partial(helper_agent_slug)(name)
        if not slug:
            raise ValueError("a pair credential needs a name")
        if not token and (not self.cap_pair_credential_held.execute(name)):
            raise ValueError(
                f"registering {name} needs the secret the pair granted us; the platform mints no credential for a repository it does not own"
            )
        {
            "name": name,
            "host": (host or "").strip() or _DEFAULT_PAIR_HOST,
            "login": (login or "").strip(),
        }
