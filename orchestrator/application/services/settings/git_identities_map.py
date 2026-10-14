"""Settings shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.settings.git_role_agents import (
    helper_git_role_agents,
)
from orchestrator.application.services.settings.identity_refs import (
    helper_identity_refs,
)
from orchestrator.domain.model.git_identity import GitIdentity


def helper_git_identities_map(
    *, config: ConfigStore | None, cap_git_roles: GitRolesPort
) -> dict[str, GitIdentity]:
    """The git identity refs the compiler injects, keyed by the catalog AGENT each step
    runs as. Only agents the operator assigned a configured identity to appear; the
    compiler gives the rest no identity, so a step whose agent is unassigned has no git
    credentials (INT-FC-R89)."""
    roles = cap_git_roles.execute()
    out: dict[str, GitIdentity] = {}
    for agent, _, _ in partial(helper_git_role_agents)():
        refs = partial(helper_identity_refs, config=config)(roles.get(agent, ""))
        if refs is not None:
            out[agent] = refs
    return out
