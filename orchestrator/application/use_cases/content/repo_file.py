"""Explicit bounded content reads keyed by observed repository revision."""

from __future__ import annotations

from typing import cast

from orchestrator.application.ports.outbound.content_cache import ContentCache
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.repository_file import RepositoryFile


class RepoFile:
    def __init__(
        self,
        *,
        source: DeliverySource | None,
        index: DeliveryIndex,
        cache: ContentCache,
    ) -> None:
        self.source = source
        self.index = index
        self.cache = cache

    def execute(self, repo: str, path: str) -> RepositoryFile:
        if self.source is None:
            raise SourceUnavailable("Content source unavailable")
        state = self.index.get(repo)
        revision = (
            state.revision
            if state is not None and path.startswith(".delivery/") and state.revision
            else self.source.content_revision(repo, path)
        )
        key = (repo, revision, path)
        value = self.cache.get(key)
        if value is not None:
            return cast(RepositoryFile, value)
        value = self.source.file(repo, path, revision=revision)
        self.cache.put(key, value)
        return value
