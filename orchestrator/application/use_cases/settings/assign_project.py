"""AssignProject over consumed application contracts."""

from __future__ import annotations

from typing import get_type_hints

from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.team_roster_store import TeamRosterStore
from orchestrator.domain.model.command_context import CommandContext


class AssignProject:
    def __init__(self, *, teams: TeamRosterStore, admission: OperationAdmission) -> None:
        self.teams = teams
        self.admission = admission

    def _execute(
        self,
        repository: str,
        team: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Assign a project to a team, or to none with an empty team: an unassigned
        project is visible to admins alone."""
        repository_id = context.repository_id(repository)
        self.teams.assign(repository_id, team.strip())
        return {"repository": repository_id, "team": team.strip()}

    def execute(
        self,
        repository: str,
        team: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.assign_project", repository)
        result = []

        def dispatch():
            value = self._execute(
                repository=repository,
                team=team,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.assign_project",
            repository,
            operation_id,
            safe_value(
                {"repository": repository, "team": team, "expected_revision": expected_revision}
            ),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repository=repository,
                team=team,
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
        repository: str,
        team: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        if team.strip() and self.teams.execute().team(team.strip()) is None:
            raise ValueError(f"there is no team named {team.strip()}")
