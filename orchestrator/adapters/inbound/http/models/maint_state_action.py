from __future__ import annotations

from pydantic import BaseModel


class MaintStateAction(BaseModel):
    acts: list[str]
    modes: list[str]
    default_mode: str
