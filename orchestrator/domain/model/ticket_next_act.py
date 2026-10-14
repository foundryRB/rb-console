"""The next observed act for an open maintenance ticket."""
from __future__ import annotations

from enum import StrEnum

__all__ = ["TicketNextAct"]


class TicketNextAct(StrEnum):
    RESOLVE = "resolve"
    REVIEW = "review"
    MERGE = "merge"
    CLOSE = "close"
