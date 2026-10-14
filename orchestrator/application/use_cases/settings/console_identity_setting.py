"""ConsoleIdentitySetting over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _CONSOLE_ROLE, _GITID
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.settings.identity_refs import (
    helper_identity_refs,
)


class ConsoleIdentitySetting:
    def __init__(
        self, *, config: ConfigStore | None, cap_git_roles: GitRolesPort
    ) -> None:
        self.config = config
        self.cap_git_roles = cap_git_roles

    def execute(self) -> str:
        """The runtime-settings NAME the console's OWN acts (merge/comment/close, plus the
        org reads) source their git token from: the identity assigned to the 'console' role
        (``gitid-<slug>``) when a configured one exists, else "" so the console has no token
        until an identity is assigned. Resolved live; the composition root reads the value via
        config.get_secret (INT-FC-R92)."""
        name = self.cap_git_roles.execute().get(_CONSOLE_ROLE, "")
        if partial(helper_identity_refs, config=self.config)(name) is not None:
            return _GITID + partial(helper_agent_slug)(name)
        return ""
