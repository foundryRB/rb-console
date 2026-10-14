"""Delivery actions from observed line state and its newest run."""
from __future__ import annotations

from collections.abc import Mapping

from orchestrator.domain.model.delivery_controls import DeliveryControls
from orchestrator.domain.model.delivery_primary_kind import DeliveryPrimaryKind

__all__ = ["derive_delivery_controls"]


def derive_delivery_controls(
    status: str,
    active_handle: str | None,
    run_phase: str | None,
    phase_records: Mapping[str, bool],
    completed_phase: str | None = None,
) -> DeliveryControls:
    available = status not in {"loading", "unavailable", "not-a-delivery"}
    in_flight = bool(active_handle) and run_phase not in {"Succeeded", "Failed", "Error", "Stopped"}
    if not available:
        primary = DeliveryPrimaryKind.UNAVAILABLE
    elif not active_handle:
        primary = DeliveryPrimaryKind.DRIVE
    elif run_phase == "Suspended":
        primary = DeliveryPrimaryKind.RESUME
    elif run_phase in {"Running", "Pending", "Stopping"}:
        primary = DeliveryPrimaryKind.RUNNING
    elif run_phase in {"Failed", "Error", "Stopped"}:
        primary = DeliveryPrimaryKind.REDRIVE
    else:
        primary = DeliveryPrimaryKind.DRIVE
    learned = status == "learned"
    phase_has_run = dict(phase_records)
    if learned and completed_phase:
        phase_has_run[completed_phase] = True
    return DeliveryControls(
        primary_kind=primary,
        run_in_flight=in_flight,
        redrive_in_flight=status == "degraded" and in_flight,
        is_learned=learned,
        close_is_next=learned and primary == DeliveryPrimaryKind.DRIVE,
        can_close=available,
        can_sign=status == "awaiting-gate" and run_phase not in {"Running", "Pending", "Stopping"},
        phase_has_run=phase_has_run,
    )
