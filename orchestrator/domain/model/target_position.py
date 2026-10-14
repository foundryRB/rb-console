"""TargetPosition domain value."""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.model.promotion_state import PromotionState
from orchestrator.domain.model.promotion_target import PromotionTarget


@dataclass(frozen=True)
class TargetPosition:
    """A target with its derived state: what it currently carries, and what act
    (if any) the operator's next move would be."""

    target: PromotionTarget
    state: PromotionState
    accepted: str = ""
    door_ref: str = ""
    detail: str = ""
    # Whether the door itself cannot be performed at all - typed rather than left
    # for a surface to sniff out of ``detail``, because it is a different act it
    # asks for (register the credential) than every other unreadable row (look at
    # the target). See derive_position's ``door_shut``.
    door_shut: bool = False

    @property
    def behind(self) -> bool:
        return self.state in (PromotionState.PENDING, PromotionState.UNPROVEN)
