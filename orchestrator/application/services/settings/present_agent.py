"""A saved agent as a caller reads it."""

from __future__ import annotations

from functools import partial

from orchestrator.application.services.settings.parse_models import helper_parse_models
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import (
    TEAM,
    USER,
    agent_level,
    may_manage,
    may_use,
)


def helper_present_agent(fields: dict, viewer: CommandContext | None) -> dict:
    """The agent's public fields, its level, who owns it as people read it (the team, or
    the person), and what the caller may do with it. The owner's principal stays here."""
    level = agent_level(fields)
    owner = ""
    if level == TEAM:
        owner = str(fields.get("owner") or "")
    elif level == USER:
        owner = str(fields.get("owner_label") or fields.get("owner") or "")
    present = {
        key: value
        for key, value in fields.items()
        if key not in {"owner", "owner_label", "level"}
    }
    return {
        **present,
        "models": partial(helper_parse_models)(fields),
        "level": level,
        "owner": owner,
        "usable": viewer is None or may_use(fields, viewer),
        "manageable": viewer is None or may_manage(fields, viewer),
    }
