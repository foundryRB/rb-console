"""Read current settings beside the observed delivery mode."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.settings.target_timeout import (
    helper_target_timeout,
)


class DeliveryConfig:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        config: ConfigStore | None,
        credentials: CredentialStore | None,
    ) -> None:
        self.observations = observations
        self.config = config
        self.credentials = credentials

    def execute(self, repo: str) -> dict:
        observed = self.observations.metadata.get(repo, {}).get("delivery_config") or {}
        selection = (
            self.config.get_setting("target-" + helper_slug(repo))
            if self.config
            else {}
        )
        selection = selection or {}
        return {
            "mode": observed.get("mode", "interactive"),
            "provider": selection.get("provider", "claude"),
            "base_url": selection.get("base_url", ""),
            "model": selection.get("model", ""),
            "agent": selection.get("agent", ""),
            "agent_level": selection.get("agent_level", ""),
            "agent_owner": selection.get("agent_owner", ""),
            "agent_owner_label": selection.get("agent_owner_label", ""),
            "timeout_seconds": helper_target_timeout(repo, config=self.config),
            "credentialed": bool(
                self.credentials and self.credentials.has_delivery(helper_slug(repo))
            ),
        }
