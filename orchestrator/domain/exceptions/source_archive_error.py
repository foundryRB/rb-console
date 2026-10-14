"""SourceArchiveError domain value."""
from __future__ import annotations


class SourceArchiveError(ValueError):
    """The archive cannot seed a repository, and the message says which files or
    which limit refused it. A ValueError, so the HTTP door answers 422."""
