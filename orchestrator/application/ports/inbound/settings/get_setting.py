"""GetSetting application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GetSettingPort(Protocol):
    def execute(self, name: str) -> dict: ...
