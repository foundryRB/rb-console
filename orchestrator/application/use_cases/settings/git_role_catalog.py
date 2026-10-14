"""GitRoleCatalog over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.services.definitions import _CONSOLE_ROLE
from orchestrator.application.services.settings.git_role_agents import (
    helper_git_role_agents,
)
from orchestrator.domain.catalog import agent_title


class GitRoleCatalog:
    def __init__(self) -> None:
        pass

    def execute(self) -> list[dict]:
        """The ordered list of assignable roles for the Settings grid: each catalog agent the
        Console hands steps to (the five phase workers, the Programmer, the Reviewer, the
        Release Manager), then the console's own acts. Each entry is its key, a human label
        naming the agent and the steps it runs, and a kind (delivery|maintenance|promotion|
        console). Derived from the bindings, so a new phase can never be silently
        un-assignable."""
        out = [
            {"key": agent, "label": f"{agent_title(agent)}: {steps}", "kind": kind}
            for agent, steps, kind in partial(helper_git_role_agents)()
        ]
        out.append(
            {
                "key": _CONSOLE_ROLE,
                "label": "console acts (merge / comment / close)",
                "kind": "console",
            }
        )
        return out
