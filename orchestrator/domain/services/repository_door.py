"""The door's line-side vocabulary: what the lines ask of a customer's repository,
in their own words rather than the host's (foundry-platform#167, ADR-044 section 6).

The ``Door`` port carries repository operations - read one pull request, list the open
ones, list the closed ones. What a ``promote/`` branch MEANS, and what a marked comment
on our ticket points at, are the promotion and maintenance lines' own knowledge, so they
live here rather than on the port. A second door implementation inherits every rule in
this module unchanged; that is the point of keeping them off the adapter.

Pure: lists and comment bodies in, positions and pointers out. Nothing here reads.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from orchestrator.domain.model.maintenance_comment import MaintenanceComment
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest

#: The branch prefix the promote act names its door for. The act names the branch for the
#: release it carries, which is what lets a merged door BE the accepted record without the
#: pair keeping any file of ours (REF-Promotion section 5: the record IS git).
DOOR_BRANCH_PREFIX = "promote/"

#: The marker a Managed resolve leaves on OUR ticket naming the pull request it opened on
#: the HOME (foundry-platform#136). A Managed app's ticket is ours and its PR is theirs, so the
#: ticket-to-PR link cannot be re-derived the way it is for an app we hold - the branch-and-text
#: rule runs over OUR PR list, and the PR is not in it. The link is RECORDED instead, on
#: the one object that is ours, and the view follows that single pointer with the pair's
#: credential rather than scanning a repository we do not own. Same idiom as the delivery
#: prompt marker: invisible in GitHub's rendered view, a stable machine handle underneath.
HOME_PR_MARKER = "<!-- foundry:home-pr "

#: The pointer's URL is the GITHUB door's shape, written by the worker entrypoint's
#: maintenance completeness check (``devops/worker-entrypoint.sh``, the marker built beside
#: FC_PAIR_HOST) and parsed here - keep the two in step. The host itself is already free
#: (any authority matches), because FC_PAIR_HOST has been a value since #131; what is
#: GitHub-shaped is the ``/pull/<n>`` path. A second door adds its own alternation here
#: rather than teaching the loop a second link idiom: Azure DevOps, the first candidate by
#: likelihood, writes ``/_git/<repo>/pullrequest/<n>``.
_HOME_PR_URL = re.compile(
    r"<!--\s*foundry:home-pr\s+https://[^/\s]+/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)\s*-->"
)


def home_pr_from_comments(
    comments: Sequence[MaintenanceComment],
) -> tuple[str, int] | None:
    """The home pull request a Managed ticket's resolve opened, read back off the marked
    comment: ``("owner/repo", number)``, or None when no comment carries the marker. The
    LATEST marked comment wins, for the same reason the delivery prompt's does - a re-drive
    that opened a fresh PR supersedes the one before it, and comments arrive oldest-first."""
    found: tuple[str, int] | None = None
    for c in comments or []:
        body = c.body
        for m in _HOME_PR_URL.finditer(body):
            found = (f"{m.group('owner')}/{m.group('repo')}", int(m.group("number")))
    return found


def _door_ref(pr: MaintenancePullRequest) -> str:
    """The ``promote/`` head ref of one listed pull request, or "" when it carries none."""
    head = pr.head_branch
    return head if head.startswith(DOOR_BRANCH_PREFIX) else ""


def open_door_ref(prs: Sequence[MaintenancePullRequest] | None) -> str:
    """The door standing open on a pair's repository, as a display reference ('PR 14').

    "" for a pair with no open door AND for a repository that could not be read: an open
    door is a positive fact, so its absence reads the same either way, and the caller
    states the unreadable case from the credential it holds rather than from this."""
    for pr in prs or []:
        if _door_ref(pr):
            return f"PR {pr.number}"
    return ""


def accepted_release(prs: Sequence[MaintenancePullRequest] | None) -> str | None:
    """The release the pair last merged, read off the newest merged ``promote/<release>``
    pull request: the promote act names its branch for the release it carries, so the merged
    door IS the accepted record.

    None when the repository could not be read, "" when the pair has merged no door. The
    difference is the whole reason this takes None rather than an empty list - a pair we
    cannot see must never read as a pair that has accepted nothing."""
    if prs is None:
        return None
    for pr in prs:
        if not pr.merged:
            continue
        ref = _door_ref(pr)
        if ref:
            return ref[len(DOOR_BRANCH_PREFIX) :].lstrip("v")
    return ""
