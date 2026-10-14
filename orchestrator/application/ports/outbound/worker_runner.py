"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.worker_launch import WorkerLaunch

__all__ = ["WorkerRunner"]


class WorkerRunner(Protocol):
    def launch(self, plan: WorkerLaunch) -> str:
        """Execute a launch plan (spawn the worker). Returns a run handle."""
        ...
