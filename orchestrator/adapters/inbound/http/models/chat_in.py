from pydantic import BaseModel

from orchestrator.adapters.inbound.http.models.chat_message import ChatMessage


class ChatIn(BaseModel):
    target: str
    phase: str = ""
    message: str
    history: list[ChatMessage] = []
    references: list[str] = []
