"""ListPairCredentials over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _PAIR


class ListPairCredentials:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self) -> list[dict]:
        """The registered pair credentials: name + host + login + whether a secret is held.
        The secret value is never listed."""
        if self.config is None:
            return []
        return self.config.list_settings(_PAIR)
