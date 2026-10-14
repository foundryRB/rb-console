"""Immutable PairCredential worker input."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PairCredential:
    """Which Secret/ConfigMap a worker's PAIR credential (FC_PAIR_TOKEN / FC_PAIR_HOST) is
    sourced from: the token another organization granted us for their repository, plus the
    host it reaches.

    Deliberately NOT a GitIdentity, though it rides the same way. An identity is who we
    COMMIT as and it is ours; a pair credential is what lets us PUSH to a repository we do
    not own, registered under the name that app's own promotion contract declares. A door
    needs both - the commit carries our identity, the push carries their grant - so they
    travel side by side and neither substitutes for the other.

    Compiling stays PURE: the service resolves the refs from its registry and passes them in;
    the compiler only names them, and the value never leaves the cluster's Secret.
    """

    secret_name: str
    host_cm: str = ""            # empty => no FC_PAIR_HOST (the entrypoint keeps github.com)
    secret_key: str = "value"
    host_key: str = "host"
