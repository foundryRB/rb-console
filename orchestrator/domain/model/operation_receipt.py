from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class OperationReceipt:
    key: str
    fingerprint: str
    state: Literal["claimed", "dispatched", "completed", "unknown"]
    secret_write: bool
    evidence: dict[str, Any]
    result: Any = None
    reason: str = ""
