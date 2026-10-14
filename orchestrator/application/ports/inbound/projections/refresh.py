"""Refresh application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RefreshPort(Protocol):
    def execute(self, *, force: bool = False) -> int: ...
