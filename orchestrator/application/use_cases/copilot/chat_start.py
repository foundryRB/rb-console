"""ChatStart over consumed application contracts."""

from __future__ import annotations

from orchestrator.application.ports.inbound.copilot.chat import ChatPort
from orchestrator.application.ports.outbound.projections.turns import TurnStore
from orchestrator.domain.model.command_context import CommandContext


class ChatStart:
    def __init__(self, *, turns: TurnStore, cap_chat: ChatPort) -> None:
        self.turns = turns
        self.cap_chat = cap_chat

    def execute(
        self,
        repo: str,
        phase: str,
        message: str,
        history=None,
        references=None,
        *,
        viewer: CommandContext | None = None,
    ) -> dict:
        """Start one project co-pilot turn in the background; the id redeems it at chat_poll."""
        return {
            "turn": self.turns.start(
                lambda: self.cap_chat.execute(
                    repo, phase, message, history, references, viewer=viewer
                )
            )
        }
