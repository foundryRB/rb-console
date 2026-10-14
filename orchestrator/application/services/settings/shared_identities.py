"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)


def helper_shared_identities(
    *, cap_git_roles: GitRolesPort, cap_list_git_identities: ListGitIdentitiesPort
) -> set[str]:
    """The set of GitHub logins the console drives AS: the identities assigned to any role.
    The maintenance derivation badges a PR authored by any of these as 'ours'; whose review
    counts is the playbook's verdict rule, which this set does not touch (INT-FC-R66). With an
    identity per catalog agent the Programmer and the Reviewer are usually different
    accounts, so 'ours' is a set, not a single login (INT-FC-R91)."""
    roles = cap_git_roles.execute()
    assigned = {v for v in roles.values() if v}
    by_name = {i.get("name", ""): i for i in cap_list_git_identities.execute()}
    logins: set[str] = set()
    for name in assigned:
        ident = by_name.get(name) or {}
        login = (ident.get("login") or ident.get("name") or name).strip()
        if login:
            logins.add(login)
    return logins
