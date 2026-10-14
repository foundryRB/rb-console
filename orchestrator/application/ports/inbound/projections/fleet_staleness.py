"""FleetStaleness application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FleetStalenessPort(Protocol):
    def execute(self) -> tuple[str | None, str]: ...
