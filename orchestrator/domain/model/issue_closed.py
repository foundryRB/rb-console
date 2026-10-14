"""Acknowledged repository command result."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IssueClosed:
    number: int
