"""Semantic committed delivery record value."""
from enum import Enum


class RecordStatus(str, Enum):
    IN_PROGRESS = "in-progress"
    COMPLETE = "complete"
    ABORTED = "aborted"
    GATE = "gate"
