"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.retained_execution import RetainedExecution

__all__ = ["RunLogStore"]


class RunLogStore(Protocol):
    """Snapshots of finished runs' logs, keyed by Workflow name. The executor GC's a
    completed run's pods long before its row leaves the list, so the service captures
    each terminal run's tail here once and log reads fall back to it."""

    def save(
        self, name: str, text: str, prune_after_seconds: int | None = None
    ) -> None:
        """Persist one run's log text (idempotent overwrite). prune_after_seconds is the
        retention horizon stored snapshots are reclaimed at - the caller passes the run
        rows' own TTL so files and rows expire together; None keeps the store's default."""
        ...

    def load(self, name: str) -> str | None:
        """The stored text for a run, or None when no snapshot exists."""
        ...

    def has(self, name: str) -> bool:
        """Whether a snapshot exists for the run (a cheap existence probe)."""
        ...

    def save_metadata(self, name: str, metadata: RetainedExecution) -> None: ...

    def all_metadata(self) -> list[RetainedExecution]:
        """Every retained run record. Raises SourceUnavailable when the archive cannot be
        read; when only some records cannot, RetainedEvidenceUnreadable carries the rest."""
        ...
