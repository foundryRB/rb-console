"""TeamRoster application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.team_roster import TeamRoster


@runtime_checkable
class TeamRosterPort(Protocol):
    def execute(self) -> TeamRoster: ...
