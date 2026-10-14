"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _GITID
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.domain.model.git_identity import GitIdentity


def helper_identity_refs(
    name: str, *, config: ConfigStore | None
) -> GitIdentity | None:
    """The ConfigMap/Secret refs for a saved identity by name; None when the name is empty
    or names no configured identity, so an unassigned role gets no identity (never a
    dangling ref, never a built-in default)."""
    slug = partial(helper_agent_slug)(name)
    if not slug or config is None:
        return None
    cm = config.get_setting(_GITID + slug) or {}
    if not cm.get("configured"):
        return None
    obj = f"fc-{_GITID}{slug}"
    return GitIdentity(
        user_cm=obj,
        user_key="name",
        email_cm=obj if cm.get("email") else "",
        email_key="email",
        secret_name=f"{obj}-key",
        secret_key="value",
    )
