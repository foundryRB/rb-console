"""Derive one repo's maintenance positions from source data (INT-FC-R58). Pure:
issues in, PRs (with reviews and checks) in, tags and unreleased commits in -
positions out. The derivation writes no file and keeps no store, so the same
inputs always yield the same positions (REF-Maintenance section 6: the issue,
the PR, the tag, and the deployment are the record homes).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from orchestrator.application.maintenance_modes import is_contributor
from orchestrator.application.release_train import derive_train
from orchestrator.application.services.maintenance.verdict import derive_verdict
from orchestrator.domain.maintenance import (
    CHECKS_GREEN,
    CHECKS_PENDING,
    CHECKS_RED,
    CHECKS_UNKNOWN,
    COMPLEXITY_LEVELS,
    PRIORITY_LEVELS,
)
from orchestrator.domain.model.issue_position import IssuePosition
from orchestrator.domain.model.maintenance_check import MaintenanceCheck
from orchestrator.domain.model.maintenance_comment import MaintenanceComment
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue
from orchestrator.domain.model.maintenance_positions import MaintenancePositions
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.maintenance_review import MaintenanceReview
from orchestrator.domain.model.pr_position import PrPosition
from orchestrator.domain.model.release_train import ReleaseTrain


def pr_resolves_ticket(head: str, title: str, body: str, ticket: int | str) -> bool:
    """Does this PR resolve ticket #n? The ONE rule shared across every maintenance surface
    (the lifecycle strip, the one-shot judge, the worker's completeness check): its branch
    carries the ticket in the resolver's ``{type}/{n}-{slug}`` convention AND its title or body
    references ``#n``. Branch-AND-text, so a coincidental branch (a ``release/7-rc`` that merely
    starts with the number) or a stray ``#n`` mention alone never qualifies, and the three
    surfaces agree on 'the PR for #n' instead of one linking a PR another parks (INT-FC-R84)."""
    n = str(ticket)
    if not re.search(rf"(^|/){re.escape(n)}-", head or ""):
        return False
    return bool(re.search(rf"#{re.escape(n)}(\D|$)", f"{title or ''}\n{body or ''}"))


#: The label the resolve skill applies to a ticket it judges too big for a maintenance scope,
#: and the HTML-comment marker it wraps the prepared delivery prompt in when it posts that
#: prompt to the ticket (issue #13). The label is the durable, operator-visible signal the
#: console reads to offer "Switch to Delivery" (it rides ``IssuePosition.labels`` like #12's
#: foundry-hidden); the marker is invisible in GitHub's rendered view but a stable machine
#: handle the console reads the prompt back off, the same convention idiom as the verdict line.
DELIVERY_SCALE_LABEL = "foundry-delivery-scale"
DELIVERY_PROMPT_MARKER = "<!-- foundry:delivery-prompt -->"

#: The label the resolve skill applies to a ticket whose fix lives in ANOTHER repo (issue
#: #35) - the locus twin of the delivery-scale label's size judgement. It rides
#: ``IssuePosition.labels`` the same way, and the pane reads it to explain why the ticket
#: has no resolve act here and to name the repo that owns the code. The console offers no
#: one-click transfer: moving an issue between repos is the operator's act on the host, and
#: a console that moved tickets on its own would relocate work no one had reviewed.
WRONG_REPO_LABEL = "foundry-wrong-repo"


def delivery_prompt_from_comments(comments: Sequence[MaintenanceComment]) -> str:
    """The prepared delivery prompt the resolve skill left on a delivery-scale ticket, read
    back off its marked comment (INT-FC-R100). The LATEST marked comment wins - a re-driven
    scope step supersedes an earlier one, and GitHub returns comments oldest-first, so a plain
    left-to-right scan keeps the last; everything after the marker is the prompt, trimmed. ""
    when no comment carries the marker (a ticket that was never judged delivery-scale), so a
    caller reads "" as "no prepared prompt" and never a half-parsed one."""
    prompt = ""
    for c in comments or []:
        body = c.body
        idx = body.rfind(DELIVERY_PROMPT_MARKER)
        if idx != -1:
            prompt = body[idx + len(DELIVERY_PROMPT_MARKER) :].strip()
    return prompt


def delivery_prompt_of(comments: Sequence[MaintenanceComment], body: str | None) -> str:
    """The customer request a switch pre-fills (INT-FC-R100): the prepared prompt off the
    ticket's latest marked comment when one holds text after the marker, else the ticket's own
    body, trimmed. A ticket the resolve worker judged is handed off through the marked comment,
    because its body is the raw ask and the brief is what the worker prepared beside it; a
    ticket authored as the brief itself (an umbrella ticket a session consolidated the ask
    into) carries no comment, and its body IS the request. "" only when the ticket has
    neither, so a caller reads "" as "nothing to pre-fill" and never a half-parsed prompt."""
    prompt = delivery_prompt_from_comments(comments)
    return prompt if prompt else (body or "").strip()


#: Home pull request pointers are parsed by domain.services.repository_door.


#: An unselected GitHub Issue Form field renders as this literal, which reads as "absent",
#: never as a value.
_NO_RESPONSE = "_no response_"


def read_ticket_signal(body: str | None, key: str, allowed: tuple[str, ...]) -> str:
    """The author-declared value for ``key`` (e.g. ``"Complexity"``) read from a clean marker
    in an issue body, matched case-insensitively against ``allowed``. Returns the canonical
    lowercased value, or "" when the marker is absent or its value is not one the Console knows
    - an unrecognised sizing is no sizing, never a wrong badge (INT-FC-R93). The same
    'author speaks a convention the tool reads' idiom as the verdict line and GitHub's
    ``Closes #3``; two shapes are read so a guided form and a bare repo both work:

    - the GitHub Issue Form field block - a ``### <key>`` heading whose next non-empty line is
      the value (what a dropdown renders; ``_No response_`` reads as absent);
    - a hand-typed trailer line ``<key>: <value>`` on its own line (a repo with no template).

    The form block wins when both are present; the first match wins within a shape."""
    text = body or ""
    allowed_l = {a.lower() for a in allowed}
    # Form field block: a heading line that is exactly the key, then the value on the next
    # non-empty line. Any heading level (Issue Forms render '### <label>').
    block = re.search(rf"(?im)^#{{1,6}}[ \t]*{re.escape(key)}[ \t]*$\n+([^\n]+)", text)
    if block:
        val = block.group(1).strip().lower()
        if val and val != _NO_RESPONSE and val in allowed_l:
            return val
    # Trailer line: 'Key: value' on its own line.
    for line in text.splitlines():
        trailer = re.match(
            rf"(?i)^[ \t]*{re.escape(key)}[ \t]*:[ \t]*(.+?)[ \t]*$", line
        )
        if trailer and trailer.group(1).strip().lower() in allowed_l:
            return trailer.group(1).strip().lower()
    return ""


def checks_state(check_runs: Sequence[MaintenanceCheck]) -> str:
    """The head commit's checks, folded to one word, fail-closed: any failure is red,
    anything unfinished is pending, no checks at all reads unknown."""
    if not check_runs:
        return CHECKS_UNKNOWN
    conclusions = [(c.status, c.conclusion) for c in check_runs]
    if any(
        conc in ("failure", "cancelled", "timed_out", "action_required")
        for _, conc in conclusions
    ):
        return CHECKS_RED
    if any(status != "completed" for status, _ in conclusions):
        return CHECKS_PENDING
    if all(conc in ("success", "neutral", "skipped") for _, conc in conclusions):
        return CHECKS_GREEN
    return CHECKS_UNKNOWN


def derive_positions(
    repo: str,
    issues: Sequence[MaintenanceIssue],
    prs: Sequence[MaintenancePullRequest],
    reviews_by_pr: dict[int, Sequence[MaintenanceReview]],
    checks_by_pr: dict[int, Sequence[MaintenanceCheck]],
    tags: list[str],
    unreleased_subjects: list[str],
    git_user: str | Iterable[str] = "",
    merger: str = "",
    deployed: str = "",
    healthy: bool | None = None,
    closed_prs: Sequence[MaintenancePullRequest] | None = None,
    default_checks: Sequence[MaintenanceCheck] | None = None,
) -> MaintenancePositions:
    """The whole loop for one repo, derived. Issues carrying a ``pull_request`` key are
    PRs wearing the issues API's clothes and are excluded from intent. ``closed_prs`` are the
    recently-closed PRs (merged or closed-unmerged): a lightweight position each (state only,
    no verdict/checks - a closed PR is terminal), so the lifecycle can resolve a ticket whose
    PR already left the open list."""
    issue_positions = tuple(
        IssuePosition(
            number=i.number,
            title=i.title,
            author=(i.author or ""),
            labels=i.labels,
            url=i.url,
            created_at=i.created_at,
            complexity=read_ticket_signal(i.body, "Complexity", COMPLEXITY_LEVELS),
            priority=read_ticket_signal(i.body, "Priority", PRIORITY_LEVELS),
            # The native GitHub Issue Type is an attribute of the issue itself (org-level,
            # not a Projects board field), so it rides the same payload - read it directly.
            type=(i.issue_type or ""),
        )
        for i in issues or []
        if not i.is_pull_request
    )
    pr_positions = tuple(
        PrPosition(
            number=p.number,
            title=p.title,
            author=(p.author or ""),
            head=(p.head_branch or ""),
            head_sha=(p.head_sha or ""),
            body=p.body or "",
            url=p.url,
            verdict=derive_verdict(
                reviews_by_pr.get(p.number, []),
                (p.author or ""),
                merger,
            ),
            checks=checks_state(checks_by_pr.get(p.number, [])),
            contributor=is_contributor((p.author or ""), git_user),
            updated_at=p.updated_at,
            state="open",
        )
        for p in prs or []
    )
    # Recently-closed PRs, terminal so no verdict/checks are derived: only their state
    # (merged vs closed-unmerged) matters, for resolving a ticket whose PR already left the
    # open list. GitHub's `merged_at` is set for a merge, null for a plain close.
    closed_positions = tuple(
        PrPosition(
            number=p.number,
            title=p.title,
            author=(p.author or ""),
            head=(p.head_branch or ""),
            url=p.url,
            updated_at=p.updated_at,
            state="merged" if p.merged else "closed",
        )
        for p in closed_prs or []
    )
    # The default branch's checks ride the train beside the deployed revision: both answer
    # "is what ships healthy", and the branch's own red is the earlier of the two signals -
    # a release that fails to publish leaves the branch red while the deployment sits happily
    # on its last good revision (the maintenance-inbox habit's step 1, third sweep).
    train: ReleaseTrain = derive_train(
        tags, unreleased_subjects, deployed, healthy, checks_state(default_checks or [])
    )
    return MaintenancePositions(
        repo=repo,
        issues=issue_positions,
        prs=pr_positions,
        train=train,
        recent_closed=closed_positions,
    )
