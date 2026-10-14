"""Read freshness and coverage of an observed projection."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SnapshotMetadataPort(Protocol):
    def execute(self, repo: str = "", *, deliveries: bool = False) -> dict: ...
