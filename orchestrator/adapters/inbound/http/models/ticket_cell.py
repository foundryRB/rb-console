from typing import Literal

from pydantic import BaseModel


class TicketCell(BaseModel):
    key: str
    label: str
    step: Literal["done", "current", "pending", "failed", "stalled"]
    detail: str
    hint: str
