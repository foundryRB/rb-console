from __future__ import annotations

from pydantic import BaseModel


class Gate(BaseModel):
    name: str
    signed_on: str | None
