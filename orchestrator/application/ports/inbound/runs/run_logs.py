"""RunLogs application capability."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RunLogsPort(Protocol):

    def execute(self, handle: str, tail: int=400, node_id: str | None=None) -> str:
        ...
