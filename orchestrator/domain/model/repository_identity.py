"""The immutable host identity behind a repository address."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryIdentity:
    repository: str
    stable_id: str

    def __post_init__(self) -> None:
        if len(self.repository.split("/")) != 2 or any(not part for part in self.repository.split("/")):
            raise ValueError("repository identity requires an owner and name")
        if not self.stable_id.isdigit() or int(self.stable_id) <= 0:
            raise ValueError("repository identity requires the host's positive numeric ID")
