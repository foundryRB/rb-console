"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.services.definitions import _CONSOLE_ROLE
from orchestrator.application.services.settings.git_role_agents import (
    helper_git_role_agents,
)


def helper_git_role_keys() -> list[str]:
    """Every assignable role's key: each catalog agent's name (already ConfigMap-safe),
    plus 'console'."""
    return [agent for agent, _, _ in partial(helper_git_role_agents)()] + [
        _CONSOLE_ROLE
    ]
