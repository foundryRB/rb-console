"""The delivery control projection carried by the browser contract."""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.domain.model.delivery_primary_kind import DeliveryPrimaryKind

__all__ = ["DeliveryControls"]


class DeliveryControls(BaseModel):
    primary_kind: DeliveryPrimaryKind
    run_in_flight: bool
    redrive_in_flight: bool
    is_learned: bool
    close_is_next: bool
    can_close: bool
    can_sign: bool
    phase_has_run: dict[str, bool]
