"""A phase in the pinned effective delivery definition."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Phase:
    name: str
    skill: str
    record: str
    gate: str
    question: str = ""
    studio: str = ""
    agent: str = ""
    label: str = ""
    completion: str = "record"
    inputs: tuple[str, ...] = ()
    artifact: str | None = None
    tool: str = ""
