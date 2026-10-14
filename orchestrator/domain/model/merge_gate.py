"""Maintenance decision vocabulary."""
from enum import StrEnum


class MergeGate(StrEnum):
    MERGE = "merge"  # recorded VERDICT: PASS + green checks: the engine merges
    PARK = "park"  # anything else: the PR waits for the operator
