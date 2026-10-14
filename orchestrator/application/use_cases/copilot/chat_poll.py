"""ChatPoll over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.outbound.projections.turns import TurnStore


class ChatPoll:
    def __init__(self, *, turns: TurnStore) -> None:
        self.turns = turns

    def execute(self, turn_id: str) -> dict:
        """One poll of a running turn: {"status": "running"} until the reply dict (or the
        turn's error) lands. An unknown id degrades to a clear error, never a hang."""
        return self.turns.poll(turn_id)
