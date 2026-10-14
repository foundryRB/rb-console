"""Authoritative repository observation and retained-settings reconciliation."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.repository_identity import RepositoryIdentity


class RepositoryIncarnations(Protocol):
    def observe(self, repository: str) -> RepositoryIdentity | None: ...

    def reconcile(
        self, repository: str, before: RepositoryIdentity | None
    ) -> RepositoryIdentity: ...

    def verify_current(self, repository: str) -> RepositoryIdentity: ...

    def adopt(self, repository: str) -> RepositoryIdentity: ...
