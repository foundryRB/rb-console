"""SourceFile domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceFile:
    """One file to land in the seed commit: its repo-relative POSIX path and bytes."""

    path: str
    data: bytes

    @property
    def text(self) -> str | None:
        """The file as UTF-8 text when it is text (no NUL byte, decodes cleanly), else
        None. Decides whether a store can inline the content or must ship a blob."""
        if b"\x00" in self.data:
            return None
        try:
            return self.data.decode("utf-8")
        except UnicodeDecodeError:
            return None
