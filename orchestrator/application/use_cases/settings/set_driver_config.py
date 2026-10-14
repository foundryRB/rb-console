"""SetDriverConfig over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.ports.inbound.settings.driver_config import (
    DriverConfigPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.driver_config import DriverConfig


class SetDriverConfig:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        cap_driver_config: DriverConfigPort,
        admission: OperationAdmission,
    ) -> None:
        self.config = config
        self.cap_driver_config = cap_driver_config
        self.admission = admission

    def _execute(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig:
        """Persist the driver agent config at runtime. An empty api_key keeps the stored one.
        A direct set is not a named agent; apply_agent_to_driver re-stamps the name."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
        self.config.put_setting(
            "driver", {"base_url": base_url, "model": model}, api_key
        )
        return self.cap_driver_config.execute()

    def execute(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig:
        context.authorize("settings.driver", "")
        result = []

        def dispatch():
            value = self._execute(
                base_url=base_url,
                model=model,
                api_key=api_key,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.driver",
            "",
            operation_id,
            safe_value(
                {
                    "base_url": base_url,
                    "model": model,
                    "api_key": api_key,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(api_key),
            validate=lambda: self._validate(
                base_url=base_url,
                model=model,
                api_key=api_key,
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
        base_url: str,
        model: str,
        api_key: str | None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig:
        """Persist the driver agent config at runtime. An empty api_key keeps the stored one.
        A direct set is not a named agent; apply_agent_to_driver re-stamps the name."""
        if self.config is None:
            raise RuntimeError("no config store is wired")
