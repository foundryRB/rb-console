"""RunMode domain value."""
from __future__ import annotations

from enum import Enum


class RunMode(str, Enum):
    """How a run treats gates. INTERACTIVE suspends at a gate and waits for a human
    signal, then resumes. ONE_SHOT closes its own gates and never suspends: a worker
    that tries to gate is a failed attempt (retried, then degraded), and a gate whose
    stamp refuses ends its step on a terminal stop (#181), so the run halts for a human
    only when it genuinely needs one. Human judgment is applied up front in one-shot.
    """

    INTERACTIVE = "interactive"
    ONE_SHOT = "one-shot"
