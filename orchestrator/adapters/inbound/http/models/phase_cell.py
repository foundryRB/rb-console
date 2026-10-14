from typing import Literal

from pydantic import BaseModel


class PhaseCell(BaseModel):
    key: str
    label: str
    record: str
    step: Literal["done", "current", "pending"]
