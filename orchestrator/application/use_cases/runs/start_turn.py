"""StartTurn over consumed application contracts."""

from __future__ import annotations

from collections.abc import Callable

from orchestrator.application.ports.outbound.projections.turns import TurnStore


class StartTurn:
    def __init__(self, *, turns: TurnStore) -> None:
        self.turns = turns

    def execute(self, fn: Callable[[], dict]) -> dict:
        """Start an arbitrary op off the wire, redeemed at chat_poll like a co-pilot turn -
        the turn store never cared what fn was (INT-FC-R55); the fleet rescan (INT-FC-R107)
        is dozens of GitHub reads, long enough to hit the same 30s proxy ceiling a synchronous
        POST does, so it rides this instead of growing its own turn machinery."""
        return {"turn": self.turns.start(fn)}
