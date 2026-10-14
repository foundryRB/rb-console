"""Resolve executor grant references against the server-owned authority archive."""

from orchestrator.application.services.operations.delegated_grants import (
    DelegatedGrants,
)
from orchestrator.domain.model.command_context import CommandContext


class ResolveDelegatedGrant:
    def __init__(self, grants: DelegatedGrants) -> None:
        self.grants = grants

    def execute(self, grant_id: str, repository: str) -> CommandContext:
        return self.grants.resolve(grant_id, repository)
