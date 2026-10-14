"""Who sees, adds, uses and drives a saved agent, by the level that owns it.

An install agent serves everyone and only an admin adds it. A team agent serves that
team's members and any member adds it. A user agent serves its owner alone and anyone
adds their own. An agent saved before levels existed is an install agent."""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.seat_refused import SeatRefused
from orchestrator.domain.model.command_context import CommandContext

INSTALL = "install"
TEAM = "team"
USER = "user"
LEVELS = (INSTALL, TEAM, USER)


def agent_level(fields: Mapping) -> str:
    level = str(fields.get("level") or "").strip()
    return level if level in LEVELS else INSTALL


def may_use(fields: Mapping, context: CommandContext) -> bool:
    """Whether the caller may apply the agent: the execution door applies install agents
    alone, and a team or user agent serves only its team or its owner."""
    level = agent_level(fields)
    owner = str(fields.get("owner") or "")
    if context.initiator_kind == "machine":
        return level == INSTALL
    if level == INSTALL:
        return True
    if level == TEAM:
        return owner in context.teams
    return bool(owner) and owner == context.principal_id


def may_manage(fields: Mapping, context: CommandContext) -> bool:
    """Whether the caller may edit or delete the agent: an admin every agent, a team
    member its team's agents, anyone their own."""
    if context.initiator_kind == "machine":
        return False
    if context.admin:
        return True
    return agent_level(fields) != INSTALL and may_use(fields, context)


def may_see(fields: Mapping, context: CommandContext) -> bool:
    return may_use(fields, context) or may_manage(fields, context)


def agent_owner(level: str, team: str, context: CommandContext) -> str:
    """The owner a new or re-levelled agent records: none for an install agent, the team
    for a team agent, the caller for a user agent. Refuses a level the caller may not add."""
    if level not in LEVELS:
        raise ValueError(f"an agent's level is one of {', '.join(LEVELS)}")
    if context.initiator_kind == "machine":
        raise PermissionDenied("The execution door adds no agent.")
    if level == INSTALL:
        if not context.admin:
            raise SeatRefused("Only an admin adds an agent for the whole install.")
        return ""
    if level == TEAM:
        if not team:
            raise ValueError("a team agent names its team")
        if team not in context.teams and not context.admin:
            raise SeatRefused(f"Only a member of {team} adds an agent for that team.")
        return team
    return context.principal_id


def refuse_foreign_seat(selection: Mapping, context: CommandContext) -> None:
    """Refuse a run on a line whose seated key the caller may not drive: another person's
    personal seat, or, through the execution door, anything but an install agent. The
    owner follows the key, so a seat's line repointed at another endpoint is still its
    owner's; a key seated from a typed credential names no owner."""
    agent = str(selection.get("agent") or "") or "a personal seat"
    level = agent_level({"level": selection.get("agent_level")})
    if context.initiator_kind == "machine" and level != INSTALL:
        raise SeatRefused(
            f"The line runs on {agent}, which is not an install agent, and the execution "
            "door drives install agents only. Apply an install agent to the line."
        )
    owner = str(selection.get("agent_owner") or "")
    if level == USER and owner != context.principal_id:
        holder = str(selection.get("agent_owner_label") or "") or "another person"
        raise SeatRefused(
            f"The line runs on {agent}, the personal seat of {holder}, and only its owner "
            "drives it. Apply a team or install agent to the line instead."
        )
