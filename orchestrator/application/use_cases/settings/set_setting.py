"""SetSetting over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.settings.named_setting import (
    helper_require_named_setting,
)
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext


class SetSetting:
    def __init__(
        self, *, config: ConfigStore | None, admission: OperationAdmission
    ) -> None:
        self.config = config
        self.admission = admission

    def _execute(
        self,
        name: str,
        fields: dict,
        secret: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Persist any named runtime setting. An empty secret keeps the stored one."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        return self.config.put_setting(name, fields, secret)

    def execute(
        self,
        name: str,
        fields: dict,
        secret: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.save", "")
        helper_require_named_setting(name)
        result = []

        def dispatch():
            value = self._execute(
                name=name,
                fields=fields,
                secret=secret,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.save",
            "",
            operation_id,
            safe_value(
                {
                    "name": name,
                    "fields": fields,
                    "secret": secret,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(secret),
            validate=lambda: self._validate(
                name=name,
                fields=fields,
                secret=secret,
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
        fields: dict,
        secret: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Persist any named runtime setting. An empty secret keeps the stored one."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
