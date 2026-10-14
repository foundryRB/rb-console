"""Maintenance decision vocabulary."""
from enum import StrEnum


class ResolveRetry(StrEnum):
    RETRY = "retry"  # a recorded FAIL with attempts remaining: re-drive on the findings
    DEGRADE = "degrade"  # a recorded FAIL with the budget spent: park for the operator
