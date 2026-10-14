from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from orchestrator.application.ports.outbound.operations.operation_receipts import (
    OperationReceipts,
)
from orchestrator.application.services.definitions import logger
from orchestrator.application.services.operations.safe_reason import (
    safe_causes,
    safe_reason,
)
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.operation_receipt import OperationReceipt


class OperationAdmission:
    """Authorize and durably claim a command before invoking its effects."""

    def __init__(self, receipts: OperationReceipts):
        self.receipts = receipts

    @staticmethod
    def key(
        context: CommandContext, action: str, repository: str, operation_id: str
    ) -> str:
        if not operation_id or len(operation_id) > 200:
            raise ValueError("A bounded operation_id is required.")
        repository = context.repository_id(repository) if repository else ""
        grant = context.grant_id if context.initiator_kind == "scheduler" else ""
        scope = [
            context.installation_id,
            context.principal_id,
            grant,
            repository,
            action,
            operation_id,
        ]
        return hashlib.sha256(
            json.dumps(scope, separators=(",", ":")).encode()
        ).hexdigest()

    def execute(
        self,
        context: CommandContext,
        action: str,
        repository: str,
        operation_id: str,
        payload: dict[str, Any],
        dispatch: Callable[[], Any],
        *,
        secret_write: bool = False,
        evidence: dict[str, Any] | None = None,
        current_authorization_revision: str | None = None,
        validate: Callable[[], None] | None = None,
        validate_retained: Callable[[OperationReceipt], None] | None = None,
    ) -> Any:
        context.authorize(
            action,
            repository,
            current_authorization_revision=current_authorization_revision,
        )
        key = self.key(context, action, repository, operation_id)
        # Secret commands retain only their scope and replay tombstone.
        fingerprint = (
            "secret-write"
            if secret_write
            else hashlib.sha256(
                json.dumps(
                    payload, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
        )
        authority = {
            "principal": context.principal_id,
            "installation": context.installation_id,
            "action": action,
            "repository": repository,
        }
        receipt, acquired = self.receipts.claim(
            key, fingerprint, authority=authority, secret_write=secret_write
        )
        if not acquired:
            if validate_retained is not None:
                validate_retained(receipt)
            if secret_write:
                raise Conflict("A secret-bearing operation key cannot be replayed.")
            if receipt.state == "completed":
                return receipt.result
            raise OperationUnknown(key)
        if validate is not None:
            try:
                validate()
            except Exception:
                self.receipts.release_claim(key)
                raise
        retained_evidence = {} if secret_write else dict(evidence or {})
        retained_evidence["authority"] = authority
        self.receipts.mark_dispatched(key, retained_evidence)
        try:
            result = dispatch()
            self.receipts.complete(key, None if secret_write else result)
            return result
        except Exception as exc:
            # From dispatch on, every failure answers an unknown outcome - even one in
            # recording the receipt - so no caller reads an effect that may have happened
            # as one that never did, and repeats it under a new key. What failed is logged,
            # kept on the receipt and returned, in a form safe for all three (INT-FC-R190).
            reason = safe_reason(exc)
            causes = safe_causes(exc)
            logger.warning(
                "operation %s (%s on %s) has no confirmed outcome: %s%s",
                key, action, repository or "-", reason, f" (from {causes})" if causes else "",
            )
            try:
                self.receipts.unknown(key, f"dispatch_outcome_unconfirmed: {reason}")
            except Exception as unrecorded:  # noqa: BLE001 - the answer below is authoritative
                logger.warning(
                    "operation %s: its unknown outcome could not be recorded (%s)",
                    key, safe_reason(unrecorded),
                )
            raise OperationUnknown(key, reason) from exc
