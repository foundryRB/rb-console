from __future__ import annotations

from pydantic import BaseModel


class RunNode(BaseModel):
    id: str
    name: str
    type: str | None
    phase: str | None
    template: str | None
    agent: str | None = None
    message: str | None
    exitCode: str | None
    children: list[str]
    startedAt: str | None
    finishedAt: str | None
    artifacts: list[str]
    refusal: str | None = None
