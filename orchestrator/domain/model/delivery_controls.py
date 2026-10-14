"""Observed delivery controls and recorded phase completion."""
from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.domain.model.delivery_primary_kind import DeliveryPrimaryKind

__all__ = ["DeliveryControls"]


@dataclass(frozen=True)
class DeliveryControls:
    primary_kind: DeliveryPrimaryKind
    run_in_flight: bool
    redrive_in_flight: bool
    is_learned: bool
    close_is_next: bool
    can_close: bool
    can_sign: bool
    phase_has_run: dict[str, bool] = field(default_factory=dict)
