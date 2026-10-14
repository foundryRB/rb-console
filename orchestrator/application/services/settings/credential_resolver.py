"""Resolve credentials from server-owned settings and distinct named scopes."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.identity.agent_slug import helper_agent_slug


class CredentialResolver:
    def __init__(self, settings: ConfigStore) -> None:
        self.settings = settings

    def console_token(self) -> str:
        roles = self.settings.get_setting("git-roles") or {}
        name = str(roles.get("console") or "")
        return (
            self.settings.get_secret("gitid-" + helper_agent_slug(name)) if name else ""
        )

    def pair_token(self, credential: str) -> str:
        return self.settings.get_secret("pair-" + helper_agent_slug(credential))

    def pair_host(self, credential: str) -> str:
        setting = (
            self.settings.get_setting("pair-" + helper_agent_slug(credential)) or {}
        )
        return str(setting.get("host") or "github.com")
