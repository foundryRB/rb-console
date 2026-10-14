from typing import Literal

from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.operation_evidence import (
    OperationEvidence,
)


class OperationReceiptResponse(BaseModel):
    operation_key: str
    state: Literal["claimed", "dispatched", "completed", "unknown"]
    reason: str
    evidence: OperationEvidence
