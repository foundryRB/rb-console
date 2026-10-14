"""GateState delivery value."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateState:
    name: str
    signed_on: str | None  # ISO date if signed, else None (pending)

    @property
    def signed(self) -> bool:
        return self.signed_on is not None
