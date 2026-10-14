"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _AGENT
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.domain.exceptions.seat_refused import SeatRefused
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import (
    INSTALL,
    USER,
    agent_level,
    may_use,
)


def helper_agent(name: str, *, config: ConfigStore | None) -> tuple[dict, str]:
    """A saved agent's fields + its credential value (server-side)."""
    if config is None:
        return ({}, "")
    fields = config.get_setting(_AGENT + partial(helper_agent_slug)(name))
    return (fields, config.get_secret(_AGENT + partial(helper_agent_slug)(name)))


def helper_refuse_unusable_agent(name: str, fields: dict, context: CommandContext) -> None:
    """Refuse applying an agent the caller may not use: another team's or another person's,
    or, through the execution door, anything but an install agent."""
    if may_use(fields, context):
        return
    if context.initiator_kind == "machine" and agent_level(fields) != INSTALL:
        raise SeatRefused(f"{name} is not an install agent, and the execution door applies install agents only.")
    raise SeatRefused(f"{name} belongs to another team or person, and is not yours to apply.")


def helper_seat(fields: dict) -> dict:
    """Who owns an applied agent, as the line records it beside its selection."""
    level = agent_level(fields)
    owner = "" if level == INSTALL else str(fields.get("owner") or "")
    label = str(fields.get("owner_label") or owner) if level == USER else owner
    return {"agent_level": level, "agent_owner": owner, "agent_owner_label": label}
