"""The contextual delivery action displayed to an operator."""
from __future__ import annotations

from enum import StrEnum

__all__ = ["DeliveryPrimaryKind"]


class DeliveryPrimaryKind(StrEnum):
    DRIVE = "drive"
    RESUME = "resume"
    RUNNING = "running"
    REDRIVE = "redrive"
    UNAVAILABLE = "unavailable"
