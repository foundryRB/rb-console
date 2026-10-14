from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class TurnStore(Protocol):
    def start(self, fn: Callable[[], dict]) -> str: ...

    def poll(self, turn_id: str) -> dict: ...
