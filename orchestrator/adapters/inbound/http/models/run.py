from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Run(BaseModel):
    handle: str
    name: str
    run_id: str | None
    mode: str | None
    kind: Literal["delivery", "maintenance", "promotion"] | None = None
    promotion: str | None = None
    maintenance: str | None = None
    ticket: str | None = None
    repo_slug: str | None = None
    repo: str | None = None
    revision: str | None = None
    phase: str
    stop: str | None = None
    created: str | None
    started: str | None
    finished: str | None
    progress: str | None = None
    agents: list[str] = None
