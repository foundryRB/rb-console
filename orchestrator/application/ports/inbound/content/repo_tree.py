"""RepoTree application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.repository_tree_entry import RepositoryTreeEntry


@runtime_checkable
class RepoTreePort(Protocol):
    def execute(self, repo: str) -> list[RepositoryTreeEntry]: ...
