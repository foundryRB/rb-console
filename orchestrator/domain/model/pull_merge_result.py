"""Acknowledged repository command result."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PullMergeResult:
    merged: bool
    commit_id: str = ""
    message: str = ""
