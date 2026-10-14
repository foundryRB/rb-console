"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

__all__ = ["CredentialStore"]


class CredentialStore(Protocol):
    def run_ref(self, run_id: str) -> str:
        """Resolve a deterministic run Secret reference without writing it."""
        ...

    def put(self, run_id: str, credential: str) -> str:
        """Store a run's worker credential in the secret store; return its ref (name).
        Only the ref is ever committed or passed downstream; the value stays here."""
        ...

    def delete(self, run_id: str) -> None:
        """Remove a finished run's credential."""
        ...

    def delivery_ref(self, slug: str) -> str:
        """The Secret name a delivery's persisted credential lives under (keyed by slug)."""
        ...

    def put_delivery(self, slug: str, credential: str) -> str:
        """Persist a delivery's model credential (namespace Secret by slug), so later drives
        and the co-pilot reuse it without re-entry. Never written to git."""
        ...

    def has_delivery(self, slug: str) -> bool:
        """Whether a delivery has a persisted credential."""
        ...

    def get_delivery(self, slug: str) -> str:
        """The delivery credential's value, server-side only (e.g. to run the co-pilot)."""
        ...

    def delete_delivery(self, slug: str) -> None:
        """Delete a target's model credential and surface any cleanup failure."""
        ...
