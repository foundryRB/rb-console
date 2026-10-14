"""PairCredentialHeld application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PairCredentialHeldPort(Protocol):
    def execute(self, name: str) -> bool: ...
