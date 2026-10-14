"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

__all__ = ["EventPublisher"]


class EventPublisher(Protocol):
    """State one past-tense fact about this console's own domains on the event bus.

    The contract is REF-Events. An implementation MUST NOT raise, block past a
    short bound, or otherwise change the outcome of the act that caused the
    publish (section 6): a publish that cannot be delivered is dropped and
    logged. ``event_type`` is one row of the console's own vocabulary
    (``application/events.py``), never composed at the call site; ``subject``
    is the id of the thing the fact is about; ``data`` carries identity and
    pointers, never a record body (section 5).
    """

    def publish(
        self, *, event_type: str, subject: str, data: dict[str, object]
    ) -> None:
        """State the fact. Never tells the caller whether it was delivered."""
        ...
