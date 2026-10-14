from __future__ import annotations

from pydantic import BaseModel


class Launch(BaseModel):
    repo: str
    phase: str
    skill: str
    has_credential: bool
    mcp_endpoints: list[str]
    prompt: str
