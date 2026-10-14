"""PairCredentialSecret over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _PAIR
from orchestrator.application.services.identity.agent_slug import helper_agent_slug


class PairCredentialSecret:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self, name: str) -> str:
        """A pair credential's value, server-side only (the door's own read). Never returned
        by an HTTP door, never written to git, never put on a command line."""
        slug = partial(helper_agent_slug)(name)
        if not slug or self.config is None:
            return ""
        return self.config.get_secret(_PAIR + slug)
