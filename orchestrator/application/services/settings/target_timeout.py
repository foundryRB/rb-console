"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import (
    _DEFAULT_TIMEOUT_SECONDS,
    _MIN_TIMEOUT_SECONDS,
    _TARGET,
)
from orchestrator.application.services.identity.slug import helper_slug


def helper_target_timeout(repo: str, *, config: ConfigStore | None) -> int:
    """Read the target setting's worker timeout, with a floored one-hour default."""
    raw = None
    if config is not None:
        sel = config.get_setting(_TARGET + partial(helper_slug)(repo)) or {}
        raw = sel.get("timeout_seconds")
    try:
        secs = int(raw) if raw not in (None, "") else _DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        secs = _DEFAULT_TIMEOUT_SECONDS
    return max(secs, _MIN_TIMEOUT_SECONDS)
