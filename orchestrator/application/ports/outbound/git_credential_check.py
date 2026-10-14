"""Application contracts for external capabilities."""

from __future__ import annotations

from typing import Protocol

__all__ = ["GitCredentialCheck"]


class GitCredentialCheck(Protocol):
    """The save-time preflight for a git identity's PAT (the git twin of DriverAgent.validate).
    A git identity was only ever checked for PRESENCE - is a Secret seated? - so a revoked or
    mis-pasted PAT first surfaced as a worker dying on an authenticated clone, mid-delivery.
    Exercising it against the repo host at save time is what makes the pane's green tick mean
    the worker will actually authenticate."""

    def validate_identity(self, token: str, login: str = "") -> tuple[bool | None, str]:
        """``(verdict, detail)``. True when the PAT authenticates and, where a ``login`` is
        declared, belongs to that account. False on an explicit refusal: a 401/403, or a PAT
        that authenticates as somebody else - two identities exist precisely so Review is a
        different account than Delivery, and a mismatch collapses that separation while still
        looking green. None on a transport failure or timeout (fail-open - an unreachable host
        is not evidence about the credential). ``detail`` names what was seen, so the operator
        reads why rather than a bare refusal."""
        ...
