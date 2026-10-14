"""StartTurn application capability."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class StartTurnPort(Protocol):
    def execute(self, fn: Callable[[], dict]) -> dict: ...
