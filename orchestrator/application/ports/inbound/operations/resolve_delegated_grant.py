from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class ResolveDelegatedGrantPort(Protocol):
    def execute(self, grant_id: str, repository: str) -> CommandContext: ...
