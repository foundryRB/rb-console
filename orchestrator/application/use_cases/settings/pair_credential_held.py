"""PairCredentialHeld over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _PAIR
from orchestrator.application.services.identity.agent_slug import helper_agent_slug


class PairCredentialHeld:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self, name: str) -> bool:
        """Whether the platform actually holds a secret under this contract-declared name.

        The one question every promotion surface asks of a `repository` target, and the one
        nothing could answer before: a contract names a credential, and this says whether
        that name resolves to anything. Presence of the RECORD is not enough - a registration
        whose secret is gone is a shut door wearing an open door's clothes."""
        slug = partial(helper_agent_slug)(name)
        if not slug or self.config is None:
            return False
        return bool((self.config.get_setting(_PAIR + slug) or {}).get("configured"))
