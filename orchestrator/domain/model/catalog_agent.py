"""CatalogAgent domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogAgent:
    """One catalog entry, as read from the playbook studio's agent roster.

    ``body`` is the paragraph the agent runs under: the corpus's system prompt for that
    worker, appended verbatim to the step's own instructions. ``permission`` is the posture's
    mode in the runtime's own vocabulary, carried as information in a headless pod (nothing
    there can stop to ask); ``writes`` is whether it may change the artifacts it works on,
    which the worker honours as a denylist of the editing tools.
    """

    name: str
    title: str
    description: str
    skills: tuple[str, ...]
    doors: tuple[str, ...]
    permission: str
    writes: bool
    fresh_eyes: bool
    body: str
