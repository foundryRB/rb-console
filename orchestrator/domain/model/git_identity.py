"""Immutable GitIdentity worker input."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GitIdentity:
    """Which ConfigMap/Secret a worker's git identity (FC_GIT_USER / FC_GIT_EMAIL /
    FC_GIT_TOKEN) is sourced from. Every identity is a saved runtime setting the operator
    configured, pointing these refs at its own ``fc-gitid-<slug>`` ConfigMap+Secret; there is
    no built-in default. A step whose catalog agent the operator assigned none gets no identity
    at all (the caller passes ``None``), so the worker has no git credentials until one is
    configured and assigned. Compiling stays PURE: the service resolves each agent's identity
    from its Settings and passes them in; the compiler only names refs.
    """

    user_cm: str
    secret_name: str
    user_key: str = "name"
    email_cm: str = ""          # empty => no FC_GIT_EMAIL (entrypoint keeps its synthetic default)
    email_key: str = "email"
    secret_key: str = "value"
