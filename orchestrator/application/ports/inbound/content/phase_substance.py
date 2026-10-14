"""PhaseSubstance application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PhaseSubstancePort(Protocol):
    def execute(self, repo: str, phase: str) -> dict: ...
