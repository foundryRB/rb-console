"""RunStatus application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RunStatusPort(Protocol):
    def execute(self, handle: str) -> str: ...
