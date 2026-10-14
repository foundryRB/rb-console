"""DeleteTeam over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.team_roster_store import TeamRosterStore
from orchestrator.domain.model.command_context import CommandContext


class DeleteTeam:
    def __init__(self, *, teams: TeamRosterStore, admission: OperationAdmission) -> None:
        self.teams = teams
        self.admission = admission

    def _execute(
        self,
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        """Delete a team and its assignments: its projects become unassigned, which an
        admin alone sees until they are assigned again."""
        self.teams.delete_team(name)

    def execute(
        self,
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        context.authorize("settings.delete_team", "")
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
            "settings.delete_team",
            "",
            operation_id,
            safe_value({"name": name, "expected_revision": expected_revision}),
            dispatch,
            secret_write=False,
            validate=lambda: None,
        )
        if result:
            return result[0]
        return restore_result(
            retained, get_type_hints(self._execute).get("return", object)
        )
