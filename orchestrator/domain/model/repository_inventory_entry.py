"""Repository identity and fleet discovery facts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryInventoryEntry:
    repository: str
    name: str
    updated_at: str | None = None
    topics: tuple[str, ...] = ()
    repository_id: str = ""
