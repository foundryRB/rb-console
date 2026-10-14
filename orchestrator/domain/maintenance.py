"""Value objects for the maintenance mode: the loop positions, the release train,
the verdict, and the ceremony mode. All derived on read from the repo host and the
pipeline (REF-Maintenance section 6): nothing here is ever stored, so the same
inputs always yield the same values.
"""
from __future__ import annotations

from collections.abc import Iterable


def identity_set(identities: str | Iterable[str] | None) -> set[str]:
    """Normalise the console's own git identities to a lowercased set of GitHub logins.

    Per-phase identities make 'ours' a set of logins, not one (a resolver that authors
    PRs, a distinct reviewer that approves them). Accepts a plain string (a one-identity
    console) or any iterable. Logins are compared case-insensitively, as GitHub logins
    are."""
    if identities is None:
        return set()
    if isinstance(identities, str):
        identities = [identities]
    return {i.strip().lower() for i in identities if i and i.strip()}




#: The verdict values a PR can read as. AWAITING is the fail-closed default: a PR with no
#: counted PASS or FAIL and no UNRECORDED review is still waiting for its review.
#: UNRECORDED is REF-Maintenance section 5's third state: a completed review whose identity
#: (the PR's author, or the merger) could record no PASS or FAIL. It is neither: nothing
#: merges on it and nothing re-drives on it, and the PR waits for an independent reviewer.
VERDICT_PASS = "pass"
VERDICT_FAIL = "fail"
VERDICT_UNRECORDED = "unrecorded"
VERDICT_AWAITING = "awaiting"

#: Checks state for a PR's head commit. UNKNOWN when the API is unreachable - which
#: blocks a one-shot merge exactly like RED does (fail-closed).
CHECKS_GREEN = "green"
CHECKS_RED = "red"
CHECKS_PENDING = "pending"
CHECKS_UNKNOWN = "unknown"

#: The author-declared sizing hint, read from a clean marker in the issue body (never a
#: label, so no repo needs to define one). Ordered low -> high; the vocabulary the parser
#: accepts and the frontend meter renders. "" (absent or unrecognised) is the fourth,
#: implicit value: no marker, no badge.
COMPLEXITY_LEVELS = ("low", "medium", "high")

#: The author-declared priority, the usual five-level scale (Jira's), read the same way.
#: Ordered lowest -> highest; the frontend renders one arrow per level. "" is absent.
PRIORITY_LEVELS = ("lowest", "low", "medium", "high", "highest")
