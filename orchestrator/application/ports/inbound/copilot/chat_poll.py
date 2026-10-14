"""ChatPoll application capability."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ChatPollPort(Protocol):
    def execute(self, turn_id: str) -> dict: ...
