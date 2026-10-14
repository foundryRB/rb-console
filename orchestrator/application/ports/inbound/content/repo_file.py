"""RepoFile application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.repository_file import RepositoryFile


@runtime_checkable
class RepoFilePort(Protocol):
    def execute(self, repo: str, path: str) -> RepositoryFile: ...
