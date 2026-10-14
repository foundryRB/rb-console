"""GitRoles over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _GIT_ROLES


class GitRoles:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self) -> dict:
        """The role -> identity-name map (which identity each phase, and the console's acts, run
        as). A missing/empty role means unassigned - no identity. Never a secret."""
        if self.config is None:
            return {}
        raw = self.config.get_setting(_GIT_ROLES) or {}
        return {k: v for k, v in raw.items() if k != "configured" and v}
