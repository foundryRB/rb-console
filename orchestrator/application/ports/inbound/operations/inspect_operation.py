from typing import Protocol, runtime_checkable

from orchestrator.domain.model.command_context import CommandContext


@runtime_checkable
class InspectOperationPort(Protocol):
    def execute(self, operation_key: str, *, context: CommandContext) -> dict: ...
