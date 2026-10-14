"""PairCredentialRef over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.services.definitions import _PAIR
from orchestrator.application.services.identity.agent_slug import helper_agent_slug


class PairCredentialRef:
    def __init__(self, *, cap_pair_credential_held: PairCredentialHeldPort) -> None:
        self.cap_pair_credential_held = cap_pair_credential_held

    def execute(self, name: str) -> str:
        """The Secret object a worker performing this pair's door sources its token from, or
        '' when nothing is held. Only the REF travels to whoever performs the act; the value
        stays here, the same contract every other worker credential travels under."""
        slug = partial(helper_agent_slug)(name)
        if not slug or not self.cap_pair_credential_held.execute(name):
            return ""
        return f"fc-{_PAIR}{slug}-key"
