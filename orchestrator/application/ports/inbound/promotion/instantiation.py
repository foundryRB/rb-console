"""Instantiation application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from orchestrator.domain.model.instantiation import Instantiation


@runtime_checkable
class InstantiationPort(Protocol):
    def execute(self, repo: str) -> Instantiation: ...
