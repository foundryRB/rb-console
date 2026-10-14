"""McpDoors application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class McpDoorsPort(Protocol):
    def execute(self) -> list[str]: ...
