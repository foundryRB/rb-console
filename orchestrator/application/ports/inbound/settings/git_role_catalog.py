"""GitRoleCatalog application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GitRoleCatalogPort(Protocol):
    def execute(self) -> list[dict]: ...
