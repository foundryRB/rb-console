"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.services.definitions import _PAIR
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.domain.model.pair_credential import PairCredential


def helper_pair_refs(
    name: str, *, cap_pair_credential_held: PairCredentialHeldPort
) -> PairCredential | None:
    """The Secret/ConfigMap refs a door worker sources this pair's credential from, or None
    when nothing is held. The compiler names refs and never values, so this is the whole of
    what leaves the console for a pair door."""
    slug = partial(helper_agent_slug)(name)
    if not slug or not cap_pair_credential_held.execute(name):
        return None
    return PairCredential(
        secret_name=f"fc-{_PAIR}{slug}-key",
        host_cm=f"fc-{_PAIR}{slug}",
        secret_key="value",
        host_key="host",
    )
