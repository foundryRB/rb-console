"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _TARGET
from orchestrator.application.services.identity.slug import helper_slug


def helper_target_selection(repo: str, *, config: ConfigStore | None) -> dict:
    """Read the target's model selection; its credential is held by the credential port."""
    if config is None:
        return {}
    sel = config.get_setting(_TARGET + partial(helper_slug)(repo)) or {}
    if any(sel.get(k) for k in ("agent", "provider", "base_url", "model")):
        return sel
    return {}
