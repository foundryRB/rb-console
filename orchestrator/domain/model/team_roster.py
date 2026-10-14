from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from orchestrator.domain.model.team import Team


def group_name(value: str) -> str:
    """A group as the identity provider names it, with or without its leading path slash."""
    return value.strip().lstrip("/")


@dataclass(frozen=True)
class TeamRoster:
    """The installation's teams and the team each assigned repository belongs to.

    An assignment names a lowercased `owner/name` repository identity. An assignment to a
    team the roster does not hold assigns nothing, so the repository reads as unassigned."""

    teams: tuple[Team, ...] = ()
    assignments: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "teams", tuple(self.teams))
        object.__setattr__(
            self,
            "assignments",
            MappingProxyType({repo.lower(): team for repo, team in dict(self.assignments).items()}),
        )

    def team(self, name: str) -> Team | None:
        return next((team for team in self.teams if team.name == name), None)

    def teams_of(self, groups: Iterable[str]) -> frozenset[str]:
        """The teams whose group is one of the caller's groups."""
        held = {group_name(group) for group in groups if group_name(group)}
        return frozenset(team.name for team in self.teams if group_name(team.group) in held)

    def team_of(self, repository_id: str) -> str:
        """The team a repository is assigned to, or "" when it is assigned to none."""
        team = self.assignments.get(repository_id.lower(), "")
        return team if self.team(team) is not None else ""

    def repositories_of(self, teams: Iterable[str]) -> frozenset[str]:
        """Every repository assigned to one of the given teams."""
        wanted = {name for name in teams if self.team(name) is not None}
        return frozenset(repo for repo, team in self.assignments.items() if team in wanted)
