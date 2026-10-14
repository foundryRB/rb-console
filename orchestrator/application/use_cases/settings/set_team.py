"""SetTeam over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.settings.team_roster_store import TeamRosterStore
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.team import Team
from orchestrator.domain.model.team_roster import group_name


class SetTeam:
    def __init__(self, *, teams: TeamRosterStore, admission: OperationAdmission) -> None:
        self.teams = teams
        self.admission = admission

    def _execute(
        self,
        name: str,
        group: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        """Save a team under its name with the identity-provider group whose members
        belong to it; saving an existing name moves the team to the given group."""
        team = Team(name.strip(), group_name(group))
        self.teams.put_team(team)
        return {"name": team.name, "group": team.group}

    def execute(
        self,
        name: str,
        group: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize("settings.team", "")
        result = []

        def dispatch():
            value = self._execute(
                name=name,
                group=group,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "settings.team",
            "",
            operation_id,
            safe_value({"name": name, "group": group, "expected_revision": expected_revision}),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                name=name,
                group=group,
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
        group: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> None:
        """A team needs a name and a group, and a group belongs to one team."""
        if not partial(helper_agent_slug)(name):
            raise ValueError("a team needs a name")
        if not group_name(group):
            raise ValueError("a team needs the group its members belong to")
        holder = next(
            (
                team.name
                for team in self.teams.execute().teams
                if team.group == group_name(group) and team.name != name.strip()
            ),
            "",
        )
        if holder:
            raise ValueError(f"the group {group_name(group)} already belongs to {holder}")
