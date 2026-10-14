"""ListAgents over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.services.definitions import _AGENT
from orchestrator.application.services.settings.present_agent import (
    helper_present_agent,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.agent_access import may_see


class ListAgents:
    def __init__(self, *, config: ConfigStore | None) -> None:
        self.config = config

    def execute(self, *, viewer: CommandContext | None = None) -> list[dict]:
        """The saved agents a viewer may see: name + provider/base_url/model + the models the
        endpoint serves + whether a credential is set, with each agent's level, its owner and
        whether the viewer may apply and edit it. An admin sees every agent; anyone else the
        install's, their teams' and their own; the execution door the install's alone. The
        credential value is never listed."""
        if self.config is None:
            return []
        return [
            helper_present_agent(fields, viewer)
            for fields in self.config.list_settings(_AGENT)
            if viewer is None or may_see(fields, viewer)
        ]
