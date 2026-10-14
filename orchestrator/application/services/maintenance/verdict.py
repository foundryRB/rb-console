"""A PR's verdict, read by the playbook's one reader (INT-FC-R66): ``decision_of`` in the
vendored inbox sweep, which applies REF-Maintenance section 5 and returns the verdict with
the review that decided it. This module only adapts the console's input to it. Pure; no
verdict is ever stored.

The console reads reviews from the REST API (``user.login``, ``author_association``,
``state``, ``body``, ``submitted_at``) in no promised order; the reader takes the GraphQL
fields (``author.login``, ``authorAssociation``) oldest first. Logins are compared
lowercased on every side: GitHub's are case-insensitive, and the merging identity's login
is typed by hand.
"""

from __future__ import annotations

from collections.abc import Sequence

from orchestrator.domain.model.maintenance_review import MaintenanceReview
from orchestrator.vendor import sweep


def _login(value: str | None) -> str:
    return (value or "").strip().lower()


def _as_read(review: MaintenanceReview) -> dict:
    return {
        "author": {"login": _login(review.author)},
        "authorAssociation": (review.association or "").strip(),
        "state": (review.state or "").strip(),
        "body": review.body or "",
    }


def decide(
    reviews: Sequence[MaintenanceReview], pr_author: str, merger: str = ""
) -> tuple[str, str]:
    """The PR's verdict and the body of the review that decided it, empty when awaiting.

    ``merger`` is the identity that would merge the PR, empty where the console merges
    nothing (a home's PR is theirs to merge). Over a FAIL the body is the reviewer's work
    order, the findings a re-drive threads into the resolve."""
    ordered = sorted(reviews or [], key=lambda r: r.submitted_at or "")
    verdict, review = sweep.decision_of(
        [_as_read(r) for r in ordered], _login(pr_author), _login(merger)
    )
    return verdict, (review or {}).get("body", "")


def derive_verdict(
    reviews: Sequence[MaintenanceReview], pr_author: str, merger: str = ""
) -> str:
    """The PR's verdict alone: one derivation, read identically by the lifecycle strip, the
    substance pane, the fleet inbox, and the one-shot judge."""
    return decide(reviews, pr_author, merger)[0]
