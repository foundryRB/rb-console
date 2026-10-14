"""GetSetting over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.settings.named_setting import (
    helper_require_named_setting,
)


class GetSetting:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self, name: str) -> dict:
        """Read any named runtime setting (public fields + configured), e.g. a per-door
        MCP credential 'mcp-playbook-studio'. Never returns the secret."""
        helper_require_named_setting(name)
        return (
            self.config.get_setting(name)
            if self.config is not None
            else {"configured": False}
        )
