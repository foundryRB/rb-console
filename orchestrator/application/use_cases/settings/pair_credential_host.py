"""PairCredentialHost over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _DEFAULT_PAIR_HOST, _PAIR
from orchestrator.application.services.identity.agent_slug import helper_agent_slug


class PairCredentialHost:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self, name: str) -> str:
        """The host a registered pair credential reaches, github.com when its registration
        carries none.

        The door's SELECTOR reads this, and it is the middle link of what makes the door
        selected per app (#167): the app's contract names the credential, the registration
        names the host, the host names the implementation. Nothing new is declared anywhere
        - the field has ridden the registry since #131 shipped, waiting for the day something
        read it as a choice rather than as a label."""
        slug = partial(helper_agent_slug)(name)
        if not slug or self.config is None:
            return _DEFAULT_PAIR_HOST
        setting = self.config.get_setting(_PAIR + slug) or {}
        return str(setting.get("host") or "").strip() or _DEFAULT_PAIR_HOST
