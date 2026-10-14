from __future__ import annotations

from pydantic import BaseModel


class ChatTurn(BaseModel):
    turn: str
