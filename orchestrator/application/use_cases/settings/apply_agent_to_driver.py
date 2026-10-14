"""ApplyAgentToDriver over consumed application contracts."""

from __future__ import annotations

from functools import partial
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
from orchestrator.application.services.settings.agent import helper_agent
from orchestrator.domain.exceptions.seat_refused import SeatRefused
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import INSTALL, agent_level
from orchestrator.domain.model.driver_config import DriverConfig


class ApplyAgentToDriver:
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
        name: str,
        model: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig:
        """Point the home co-pilot's driver at a saved agent (copies its endpoint + credential)
        and remember the agent's name, so Settings shows WHICH agent answers on the Fleet page.
        The model is chosen SEPARATELY (R73): the agent's default unless one is given."""
        fields, credential = partial(helper_agent, config=self.config)(name)
        if agent_level(fields) != INSTALL:
            raise SeatRefused(
                f"The home co-pilot answers everyone, so it takes an install agent; {name} is not one."
            )
        if not credential:
            raise ValueError(f"agent {name!r} has no credential")
        chosen = model if model else fields.get("model", "")
        self.config.put_setting(
            "driver",
            {"base_url": fields.get("base_url", ""), "model": chosen, "agent": name},
            credential,
        )
        return self.cap_driver_config.execute()

    def execute(
        self,
        name: str,
        model: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig:
        context.authorize("settings.apply_driver", "")
        result = []

        def dispatch():
            value = self._execute(
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
            "settings.apply_driver",
            "",
            operation_id,
            safe_value(
                {"name": name, "model": model, "expected_revision": expected_revision}
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
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
        name: str,
        model: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriverConfig:
        """Point the home co-pilot's driver at a saved agent (copies its endpoint + credential)
        and remember the agent's name, so Settings shows WHICH agent answers on the Fleet page.
        The model is chosen SEPARATELY (R73): the agent's default unless one is given."""
        fields, credential = partial(helper_agent, config=self.config)(name)
        if agent_level(fields) != INSTALL:
            raise SeatRefused(
                f"The home co-pilot answers everyone, so it takes an install agent; {name} is not one."
            )
        if not credential:
            raise ValueError(f"agent {name!r} has no credential")
        model if model else fields.get("model", "")
