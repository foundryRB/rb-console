from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.models.chat_turn_poll import ChatTurnPoll

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/chat/turns/{turn_id}",
        response_model=ChatTurnPoll,
        response_model_exclude_unset=True,
    )
    def chat_turn(turn_id: str) -> dict:
        return service.chat_poll.execute(turn_id)

    return router
