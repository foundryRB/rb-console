"""PromotionState domain value."""
from __future__ import annotations

from enum import Enum


class PromotionState(str, Enum):
    """Where one target stands, derived from proven against accepted.

    PENDING is proven ahead of accepted with no door in flight; IN_FLIGHT is a
    door submitted and not yet landed; UNPROVEN is deployed while the declared
    acceptance does not answer; CURRENT is nothing to do. UNREADABLE is the
    honest fifth: the target's own state could not be read, which is never
    guessed at (REF-Promotion section 6 anti-pattern 8's sibling: a state we
    cannot see is reported as unseen, never as current)."""

    UNPROVEN = "unproven"
    IN_FLIGHT = "in-flight"
    PENDING = "pending"
    CURRENT = "current"
    UNREADABLE = "unreadable"
