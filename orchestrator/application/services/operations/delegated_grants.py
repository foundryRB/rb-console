"""Persist authority in the server archive and put only opaque references in runs."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256

from orchestrator.application.ports.outbound.operations.operation_receipts import (
    OperationReceipts,
)
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.delegated_grant import delegated_grant


class DelegatedGrants:
    def __init__(
        self, receipts: OperationReceipts, authorization_revision: str
    ) -> None:
        self.receipts = receipts
        self.authorization_revision = authorization_revision

    def issue(
        self, context: CommandContext, repo: str, run_id: str, timeout_seconds: int
    ) -> dict:
        context.authorize("maintenance.drive", repo)
        identity = [
            context.installation_id,
            context.principal_id,
            context.grant_id,
            context.repository_id(repo),
            run_id,
        ]
        grant_id = sha256(
            json.dumps(identity, separators=(",", ":")).encode()
        ).hexdigest()
        existing = self.receipts.get_grant(grant_id)
        if existing is None:
            values = delegated_grant(context, repo, run_id, timeout_seconds)
            values["grant_id"] = grant_id
            self.receipts.save_grant(grant_id, values)
        return {"grant_id": grant_id}

    def resolve(self, grant_id: str, repository: str) -> CommandContext:
        values = self.receipts.get_grant(grant_id)
        if values is None:
            raise PermissionDenied("The executor carries no server-issued grant")
        values = dict(values)
        values["expires_at"] = datetime.fromisoformat(values["expires_at"])
        context = CommandContext(**values)
        context.authorize(
            "maintenance.reconcile",
            repository,
            current_authorization_revision=self.authorization_revision,
        )
        return context
