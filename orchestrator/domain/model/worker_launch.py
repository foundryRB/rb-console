"""WorkerLaunch domain value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerLaunch:
    """A deterministic plan to launch one phase's worker. The orchestrator builds
    this by pure code; a WorkerRunner adapter executes it. Building it needs no
    model. Executing it is the single model step in the drive path.
    """

    repo: str
    phase: str
    skill: str
    credential_ref: str
    mcp_endpoints: tuple[str, ...]
    prompt: str
