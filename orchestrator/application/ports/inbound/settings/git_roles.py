"""GitRoles application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GitRolesPort(Protocol):
    def execute(self) -> dict: ...
