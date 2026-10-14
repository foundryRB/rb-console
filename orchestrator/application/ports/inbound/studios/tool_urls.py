"""ToolUrls application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.lifecycle_definition import LifecycleDefinition


@runtime_checkable
class ToolUrlsPort(Protocol):
    def execute(self, definition: LifecycleDefinition) -> dict[str, str]: ...
