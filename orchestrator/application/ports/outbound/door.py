"""Repository home evidence read with the contract-selected pair credential."""

from __future__ import annotations

from typing import Protocol

from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest


class Door(Protocol):
    """A home read uses only the named pair's grant. Unconfigured authority or host
    returns None; an unavailable remote source raises SourceUnavailable. A successful
    empty listing is an empty tuple, distinct from an unreadable home."""

    def repository_revision(self, repo: str, branch: str, credential: str) -> str:
        """The immutable home revision reachable by the pair credential."""
        ...

    def pull_request(
        self, repo: str, number: int, credential: str
    ) -> MaintenancePullRequest | None:
        """One normalized home pull request, including its reviews and checks."""
        ...

    def open_pull_requests(
        self, repo: str, base: str, credential: str
    ) -> tuple[MaintenancePullRequest, ...] | None:
        """Open requests against the declared base, newest first."""
        ...

    def closed_pull_requests(
        self, repo: str, base: str, credential: str
    ) -> tuple[MaintenancePullRequest, ...] | None:
        """Recently closed requests, carrying their merged disposition."""
        ...
