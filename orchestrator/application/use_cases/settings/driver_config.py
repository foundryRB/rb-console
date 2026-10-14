"""DriverConfig over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.domain.model.driver_config import DriverConfig as DomainDriverConfig


class DriverConfig:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self) -> DomainDriverConfig:
        """The current driver agent config (never the api_key value)."""
        if self.config is None:
            return DomainDriverConfig()
        d = self.config.get_setting("driver")
        return DomainDriverConfig(
            d.get("base_url", ""),
            d.get("model", ""),
            d.get("configured", False),
            d.get("agent", ""),
        )
