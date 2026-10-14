"""ListGitIdentities over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _GITID


class ListGitIdentities:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self) -> list[dict]:
        """The saved git identities: display name + commit email + GitHub login + whether a
        token is set. The token value is never listed."""
        if self.config is None:
            return []
        return self.config.list_settings(_GITID)
