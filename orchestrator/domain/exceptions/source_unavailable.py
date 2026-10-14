"""Failure to obtain an authoritative source observation."""
from __future__ import annotations

__all__ = ["SourceUnavailable"]


class SourceUnavailable(RuntimeError):
    """The source could not be observed; retained observations remain valid history."""

    def __init__(self, message: str, *, retry_after: float = 30) -> None:
        import math
        super().__init__(message)
        self.retry_after = float(retry_after) if isinstance(retry_after, (int, float)) and math.isfinite(retry_after) and retry_after > 0 else 30.0
