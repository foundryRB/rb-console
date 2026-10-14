"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.services.definitions import _CONSOLE_ROLE


def helper_merger(
    *, cap_git_roles: GitRolesPort, cap_list_git_identities: ListGitIdentitiesPort
) -> str:
    """The GitHub login the console merges as: the identity assigned to its own acts,
    empty when none is. A review by it records no verdict (INT-FC-R66): the reviewer is
    never the merger."""
    name = cap_git_roles.execute().get(_CONSOLE_ROLE, "")
    if not name:
        return ""
    ident = next(
        (i for i in cap_list_git_identities.execute() if i.get("name") == name), {}
    )
    return (ident.get("login") or ident.get("name") or name).strip()
