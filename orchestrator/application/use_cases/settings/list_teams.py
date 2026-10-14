"""ListTeams over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.settings.team_roster import TeamRosterPort
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext


class ListTeams:
    def __init__(self, *, cap_team_roster: TeamRosterPort) -> None:
        self.cap_team_roster = cap_team_roster

    def execute(self, *, viewer: CommandContext) -> dict:
        """The teams, each with its group and its projects, for an admin alone."""
        if not viewer.admin:
            raise PermissionDenied("Only an admin reads the teams.")
        roster = self.cap_team_roster.execute()
        return {
            "teams": [
                {
                    "name": team.name,
                    "group": team.group,
                    "repositories": sorted(roster.repositories_of([team.name])),
                }
                for team in roster.teams
            ]
        }
