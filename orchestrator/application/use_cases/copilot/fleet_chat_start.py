"""FleetChatStart over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.copilot.fleet_chat import FleetChatPort
from orchestrator.application.ports.outbound.projections.turns import TurnStore
from orchestrator.domain.model.command_context import CommandContext


class FleetChatStart:
    def __init__(self, *, turns: TurnStore, cap_fleet_chat: FleetChatPort) -> None:
        self.turns = turns
        self.cap_fleet_chat = cap_fleet_chat

    def execute(
        self, message: str, history=None, *, viewer: CommandContext | None = None
    ) -> dict:
        """Start one HOME co-pilot turn in the background; the id redeems it at chat_poll."""
        return {
            "turn": self.turns.start(
                lambda: self.cap_fleet_chat.execute(message, history, viewer=viewer)
            )
        }
