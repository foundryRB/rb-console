"""PairCredentialRef application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PairCredentialRefPort(Protocol):
    def execute(self, name: str) -> str: ...
