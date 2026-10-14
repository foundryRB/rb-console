"""Studios application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.studio_health import StudioHealth


@runtime_checkable
class StudiosPort(Protocol):
    def execute(self) -> list[StudioHealth]: ...
