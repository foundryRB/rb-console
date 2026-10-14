"""DeliveryConfig over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.services.definitions import _MODES
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.settings.has_delivery_cred import (
    helper_has_delivery_cred,
)
from orchestrator.application.services.settings.raw_config import helper_raw_config
from orchestrator.application.services.settings.target_selection import (
    helper_target_selection,
)
from orchestrator.application.services.settings.target_timeout import (
    helper_target_timeout,
)


class CollectDeliveryConfig:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        credentials: CredentialStore | None,
        source: DeliverySource | None,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.source = source

    def execute(self, repo: str) -> dict:
        """Collect the committed line mode beside current target settings and credential presence."""
        cfg = partial(helper_raw_config, source=self.source)(repo)
        mode = cfg.get("mode") if cfg.get("mode") in _MODES else "interactive"
        sel = partial(helper_target_selection, config=self.config)(repo)
        return {
            "mode": mode,
            "provider": sel.get("provider", "claude"),
            "base_url": sel.get("base_url", ""),
            "model": sel.get("model", ""),
            "agent": sel.get("agent", ""),
            "agent_level": sel.get("agent_level", ""),
            "agent_owner": sel.get("agent_owner", ""),
            "agent_owner_label": sel.get("agent_owner_label", ""),
            "timeout_seconds": partial(helper_target_timeout, config=self.config)(repo),
            "credentialed": partial(
                helper_has_delivery_cred, credentials=self.credentials
            )(partial(helper_slug)(repo)),
        }
