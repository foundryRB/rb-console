"""The installation's teams and project assignments, held in the console's settings.

A team is the setting `team-<name>` (its name and identity-provider group); an
assignment is the setting `project-<repo>` (the repository identity and its team). Both
are read on every admitted request, so the roster is held for a short while and dropped
the moment the console writes either; the hold bounds an edit made outside the console."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.team import Team
from orchestrator.domain.model.team_roster import TeamRoster, group_name

_TEAM = "team-"
_PROJECT = "project-"
_HOLD_SECONDS = 30.0


def team_setting(name: str) -> str:
    return _TEAM + partial(helper_agent_slug)(name)


def project_setting(repository_id: str) -> str:
    return _PROJECT + partial(helper_slug)(repository_id).lower()


class TeamRosterStore:
    def __init__(
        self,
        config: ConfigStore | None,
        *,
        hold_seconds: float = _HOLD_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.hold_seconds = hold_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._roster: TeamRoster | None = None
        self._read_at = 0.0

    def execute(self) -> TeamRoster:
        """The current roster. A read that fails keeps serving the last one it read for
        another hold before it tries again, so a slow store is read once per hold rather
        than once per request; with none read yet, the failure is the answer."""
        with self._lock:
            if self._roster is not None and self.clock() - self._read_at < self.hold_seconds:
                return self._roster
            try:
                roster = self._read()
            except SourceUnavailable:
                if self._roster is None:
                    raise
                self._read_at = self.clock()
                return self._roster
            self._roster, self._read_at = roster, self.clock()
            return roster

    def _read(self) -> TeamRoster:
        if self.config is None:
            return TeamRoster()
        teams = []
        for fields in self.config.list_settings(_TEAM):
            name = str(fields.get("name") or "").strip()
            group = group_name(str(fields.get("group") or ""))
            if name and group:
                teams.append(Team(name, group))
        assignments = {}
        for fields in self.config.list_settings(_PROJECT):
            repository = str(fields.get("repository") or "").strip().lower()
            team = str(fields.get("team") or "").strip()
            if repository and team:
                assignments[repository] = team
        return TeamRoster(tuple(sorted(teams, key=lambda team: team.name)), assignments)

    def invalidate(self) -> None:
        with self._lock:
            self._roster = None

    def put_team(self, team: Team) -> None:
        self._require().put_setting(team_setting(team.name), {"name": team.name, "group": team.group}, None)
        self.invalidate()

    def delete_team(self, name: str) -> None:
        """Delete a team and every assignment to it, so none of its projects outlives it."""
        store = self._require()
        for fields in store.list_settings(_PROJECT):
            if str(fields.get("team") or "") == name and fields.get("repository"):
                store.delete_setting(project_setting(str(fields["repository"])))
        store.delete_setting(team_setting(name))
        self.invalidate()

    def assign(self, repository_id: str, team: str) -> None:
        """Assign a repository to a team, or to none when the team is empty."""
        store = self._require()
        name = project_setting(repository_id)
        held = str(store.get_setting(name).get("repository") or "").lower()
        if held and held != repository_id.lower():
            raise ValueError(
                f"{repository_id} shares its settings name with {held}; rename one of them to assign it"
            )
        if team:
            store.put_setting(name, {"repository": repository_id.lower(), "team": team}, None)
        else:
            store.delete_setting(name)
        self.invalidate()

    def _require(self) -> ConfigStore:
        if self.config is None:
            raise SourceUnavailable("team settings are unavailable")
        return self.config
