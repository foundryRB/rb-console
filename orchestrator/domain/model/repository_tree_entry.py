"""One repository content node."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RepositoryTreeEntry:
    path: str
    kind: Literal["file", "directory", "submodule"]
    size: int | None = None
