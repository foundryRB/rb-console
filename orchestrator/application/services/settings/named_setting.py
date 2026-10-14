"""The settings the named-setting door reads and writes."""

from __future__ import annotations

from orchestrator.application.services.definitions import _RETENTION_SETTING
from orchestrator.domain.exceptions.permission_denied import PermissionDenied

_DOOR_PREFIX = "mcp-"


def helper_require_named_setting(name: str) -> None:
    """The run retention and each MCP door's credential are named settings. Every other
    setting (an agent, a target, a team, a git identity, a pair credential) has its own
    door and its own rule for who writes it."""
    if name != _RETENTION_SETTING and not (name.startswith(_DOOR_PREFIX) and len(name) > len(_DOOR_PREFIX)):
        raise PermissionDenied("The setting is not a named setting.")
