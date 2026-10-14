from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.chat_message import ChatMessage


class FleetChatIn(BaseModel):
    message: str
    history: list[ChatMessage] = []
