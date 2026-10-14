"""DriverConfig application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.driver_config import DriverConfig


@runtime_checkable
class DriverConfigPort(Protocol):
    def execute(self) -> DriverConfig: ...
