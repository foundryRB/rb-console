"""Explicit bounded content reads keyed by observed repository revision."""

from __future__ import annotations

from typing import cast

from orchestrator.application.ports.outbound.content_cache import ContentCache
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.repository_tree_entry import RepositoryTreeEntry


class RepoTree:
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

    def execute(self, repo: str) -> list[RepositoryTreeEntry]:
        if self.source is None:
            raise SourceUnavailable("Content source unavailable")
        state = self.index.get(repo)
        revision = self.source.content_revision(repo)
        scratch_revision = state.revision if state is not None else ""
        key = (repo, revision + ":" + scratch_revision, "tree")
        value = self.cache.get(key)
        if value is not None:
            return cast(list[RepositoryTreeEntry], value)
        value = self.source.tree(
            repo, revision=revision, scratch_revision=scratch_revision
        )
        self.cache.put(key, value)
        return value
