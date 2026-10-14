"""Read a durable operation's safe outcome within its caller's current authority."""

import re

from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext


class InspectOperation:
    def __init__(self, admission: OperationAdmission):
        self.admission = admission

    def execute(self, operation_key: str, *, context: CommandContext) -> dict:
        if not re.fullmatch(r"[a-f0-9]{64}", operation_key):
            raise ValueError("Invalid operation key.")
        receipt = self.admission.receipts.get(operation_key)
        authority = receipt.evidence.get("authority", {}) if receipt else {}
        if (
            authority.get("principal") != context.principal_id
            or authority.get("installation") != context.installation_id
        ):
            raise PermissionDenied("The operation is unavailable to this principal.")
        repository = authority.get("repository") or receipt.evidence.get(
            "repository", ""
        )
        context.authorize(authority.get("action", ""), repository)
        fields = ("repository", "handle", "resource_version", "uid")
        evidence = {
            key: str(receipt.evidence[key])
            for key in fields
            if receipt.evidence.get(key)
        }
        if repository:
            evidence["repository"] = repository
        return {
            "operation_key": receipt.key,
            "state": receipt.state,
            "reason": receipt.reason,
            "evidence": evidence,
        }
