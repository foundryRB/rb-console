"""Acknowledged application lifecycle state."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AppLifecycleResult:
    name: str
    paused: bool
    status: str | None = None
