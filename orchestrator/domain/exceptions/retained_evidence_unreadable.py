"""Retained run records the archive holds but cannot read."""
from __future__ import annotations

from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.retained_execution import RetainedExecution

__all__ = ["RetainedEvidenceUnreadable"]


class RetainedEvidenceUnreadable(SourceUnavailable):
    """Some retained records cannot be read. The read is unavailable all the same, so the
    archive never passes for complete; ``retained`` carries every record that could be read,
    so an unreadable record withholds only itself."""

    def __init__(
        self, unreadable: tuple[str, ...], retained: tuple[RetainedExecution, ...]
    ) -> None:
        named = ", ".join(unreadable[:3]) + (", ..." if len(unreadable) > 3 else "")
        super().__init__(
            f"Retained execution evidence is unreadable: {len(unreadable)} record(s) ({named})."
        )
        self.unreadable = unreadable
        self.retained = retained
