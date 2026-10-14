"""Text content from one approved repository revision."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    content: str
    size: int
