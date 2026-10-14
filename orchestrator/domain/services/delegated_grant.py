"""Issue the bounded reconciliation grant of an explicitly authorized one-shot run."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orchestrator.domain.model.command_context import CommandContext


def delegated_grant(
    context: CommandContext, repo: str, run_id: str, timeout_seconds: int
) -> dict:
    context.authorize("maintenance.drive", repo)
    expires = datetime.now(UTC) + timedelta(seconds=max(3600, timeout_seconds + 3600))
    if context.expires_at is not None:
        expires = min(expires, context.expires_at)
    return {
        "principal_id": context.principal_id,
        "initiator_kind": "scheduler",
        "grant_id": context.grant_id + ":" + run_id,
        "allowed_actions": [
            "maintenance.reconcile",
            *sorted(
                context.allowed_actions
                & {"maintenance.drive", "maintenance.merge", "runs.archive"}
            ),
        ],
        "repositories": [context.repository_id(repo)],
        "authorization_revision": context.authorization_revision,
        "installation_id": context.installation_id,
        "expires_at": expires.isoformat(),
    }
