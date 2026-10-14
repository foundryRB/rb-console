"""Derive the maintenance inbox: one attention queue across every maintained repo, most
urgent first (REF-Maintenance.md section 7).

The sweep the inbox habit runs, and the single home of the queue's rules so that a
session, a console and a desk cannot each drift into their own (section 8: the inbox
contract's enforcement home). It is also the home of the one verdict reader
(``decision_of``): the merge helper loads it from here, so the queue and the merge act read
a PR's reviews by the same rules. Two layers, deliberately split:

  - ``derive_inbox`` is PURE - positions in, ordered queue out, no I/O at all. It is what
    ``fixtures/`` pins, what this repo's suite runs, and what another runtime is attested
    against when it re-implements the derivation rather than importing this one;
  - the reads below shell ``gh`` to build those positions. They are replaceable: any caller
    that already holds the positions (a console that polls the host itself) calls the pure
    layer directly and skips them.

Positions and rows are plain JSON-shaped dicts rather than dataclasses, because the
fixture corpus is JSON and a second runtime must read the same bytes. A position may
carry a ``promotion`` list (one entry per declared target, as REF-Promotion derives it);
a reader that does not read contracts simply omits it, derives a queue with no promotion
rows, and declares the signal unchecked.

Needs the repo host CLI (``gh``) authenticated for the reads; stdlib only otherwise. Usage:

    python sweep.py --org <name>
    python sweep.py --repos <owner/name>,<owner/name> --json
    python sweep.py --org <name> --running <owner/name>:resolve:12,<owner/name>:review:34
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# The vocabulary (section 7). One word means one thing across every reader.
# ---------------------------------------------------------------------------

CHECKS_GREEN, CHECKS_RED, CHECKS_PENDING, CHECKS_UNKNOWN = "green", "red", "pending", "unknown"
VERDICT_PASS, VERDICT_FAIL, VERDICT_AWAITING = "pass", "fail", "awaiting"
#: Section 5's third state: a review that happened and could not be recorded, because the
#: reviewing identity is the PR's author or the merger. It is not a failure and not a
#: mergeable verdict, so the queue files it with `awaiting` - the act is still `review`,
#: and only the wording changes, to say the PR needs an INDEPENDENT reviewer.
VERDICT_UNRECORDED = "unrecorded"

#: The corpus mark for "keep this off the maintenance surfaces", applied by `resolve-ticket`
#: when a ticket becomes delivery-scale and by an operator holding one back deliberately.
HIDDEN_LABEL = "foundry-hidden"

#: Attention order (section 7): what is being worked RIGHT NOW leads, so a reader does not
#: put a second worker on it; then what is broken, then what waits on a human, then what
#: merged but never shipped, then what a proven release has not reached, then open intent.
URGENCY = {
    "running": 0,
    "red-ci": 1,
    "drift": 2,
    "pr-review": 3,
    "unreleased": 4,
    "promotion": 5,
    "issue": 6,
}

#: Terminal-bad check conclusions. A timed-out or cancelled run is red, never left wearing
#: the muted pending state forever.
_RED_CONCLUSIONS = {
    "FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE",
}
_GREEN_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}

#: The last VERDICT token a review body carries, read wherever it lands and tolerant of
#: markdown emphasis and trailing prose (section 5).
_VERDICT = re.compile(r"VERDICT:\s*(PASS|FAIL|UNRECORDED)", re.IGNORECASE)

#: The author associations a review counts from: the repo's owner, a member of its
#: organisation, or an invited collaborator. A review carrying any other association, or
#: none, counts for nothing: on a public repo anyone can post a review, and a verdict
#: authorizes a merge.
_WRITERS = {"OWNER", "MEMBER", "COLLABORATOR"}


def pr_resolves_ticket(head: str, title: str, body: str, ticket: int | str) -> bool:
    """Does this PR resolve ticket #n? The one rule every maintenance surface shares: its
    branch carries the ticket in the ``{type}/{n}-{slug}`` convention (section 2) AND its
    title or body references ``#n``. Branch-AND-text, so neither a coincidental branch (a
    ``release/7-rc`` that merely starts with the number) nor a stray ``#n`` mention alone
    qualifies, and every reader agrees on "the PR for #n"."""
    n = str(ticket)
    if not re.search(rf"(^|/){re.escape(n)}-", head or ""):
        return False
    return bool(re.search(rf"#{re.escape(n)}(\D|$)", f"{title or ''}\n{body or ''}"))


def decision_of(reviews: list[dict], author: str = "", merger: str = "") -> tuple[str, dict | None]:
    """The PR's verdict (section 5) and the review that decided it: the one walk every
    reader of a verdict runs, pinned by ``fixtures/verdict/verdict-reader.json``.

    ``reviews`` are the PR's reviews oldest first, as the host returns them (``state``,
    ``body``, ``author.login``, ``authorAssociation``); ``author`` is the PR's author and
    ``merger`` the identity that would merge, empty when the caller merges nothing.

      - Only a review bearing a ``VERDICT:`` token takes part, and its last token is its
        verdict. A review whose author is not the repo's owner, a member of its organisation or an
        invited collaborator (its ``authorAssociation``) takes no part at all.
      - A review by the PR's author or by the merger is UNRECORDED, whatever its token and
        its state: it records no verdict.
      - Any other review counts a PASS on an approving review and a FAIL on an approving or
        a request-changes review. A token in a plain comment is not a verdict, except
        UNRECORDED, which is defined to ride one.
      - The last counted PASS or FAIL decides. Only when there is none does UNRECORDED
        decide, as the last review that recorded nothing: it never outranks a counted
        verdict.

    The review is None exactly when the verdict is awaiting."""
    counted: tuple[str, dict] | None = None
    unrecorded: dict | None = None
    for review in reviews or []:
        tokens = _VERDICT.findall(review.get("body") or "")
        if not tokens or (review.get("authorAssociation") or "").upper() not in _WRITERS:
            continue
        login = (review.get("author") or {}).get("login") or ""
        token, state = tokens[-1].upper(), (review.get("state") or "").upper()
        if token == "UNRECORDED" or (login and login in (author, merger)):
            unrecorded = review
        elif token == "PASS" and state == "APPROVED":
            counted = (VERDICT_PASS, review)
        elif token == "FAIL" and state in ("APPROVED", "CHANGES_REQUESTED"):
            counted = (VERDICT_FAIL, review)
    if counted:
        return counted
    if unrecorded is not None:
        return VERDICT_UNRECORDED, unrecorded
    return VERDICT_AWAITING, None


def verdict_of(reviews: list[dict], author: str = "", merger: str = "") -> str:
    """The PR's verdict word alone, read by ``decision_of``."""
    return decision_of(reviews, author, merger)[0]


def checks_of(rollup: list[dict] | None) -> str:
    """The head commit's checks folded to one word, fail-closed. No checks at all reads
    unknown: a repo without CI never shows a green it did not earn."""
    if not rollup:
        return CHECKS_UNKNOWN
    states = [
        (c.get("conclusion") or c.get("state") or c.get("status") or "").upper()
        for c in rollup
    ]
    if any(s in _RED_CONCLUSIONS for s in states):
        return CHECKS_RED
    if all(s in _GREEN_CONCLUSIONS for s in states):
        return CHECKS_GREEN
    return CHECKS_PENDING


# ---------------------------------------------------------------------------
# The train (section 7: red-ci on the default branch, unreleased). Pure, like the
# derivation: a host read in, a train out, so the read side is testable without a host.
# ---------------------------------------------------------------------------

#: A tag the train can count from: ``v1.2.3`` or ``1.2.3``, the prefix kept as found.
_SEMVER = re.compile(r"^(?P<prefix>v?)(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
#: A Conventional Commits subject: ``type(scope)!: text``, the scope and the marker optional.
_SUBJECT = re.compile(r"^(?P<type>[a-z]+)(\([^)]*\))?(?P<bang>!)?:\s")
#: What a subject cuts, by the rule the shared CI's release engine runs (semantic-release's
#: commit-analyzer defaults, on top of the Conventional Commits grammar): a breaking change
#: a major, a ``feat`` a minor, a ``fix``, a ``perf`` or a ``revert`` a patch, and every
#: other type nothing at all.
_BUMP = {"feat": "minor", "fix": "patch", "perf": "patch", "revert": "patch"}
_BUMP_RANK = {"": 0, "patch": 1, "minor": 2, "major": 3}


def bump_of(subjects: list[str]) -> str:
    """The bump a tail of commit subjects would cut: ``major``, ``minor``, ``patch``, or the
    empty string when nothing in the tail is releasable. Read off the subject line: the
    ``!`` marker is where the convention puts a breaking change, and the commit hygiene
    every release flows through holds each subject to that grammar."""
    bump = ""
    for subject in subjects or []:
        found = _SUBJECT.match((subject or "").strip())
        if not found:
            continue
        this = "major" if found.group("bang") else _BUMP.get(found.group("type"), "")
        if _BUMP_RANK[this] > _BUMP_RANK[bump]:
            bump = this
    return bump


def next_version_of(version: str, subjects: list[str]) -> str:
    """The version the train would cut next from ``version`` over ``subjects``, or the empty
    string when the tail cuts nothing: a docs-only tail is not unreleased work, because
    ``release`` is not an act anyone can take on it. A version that is not semver derives
    nothing either; the caller reports it rather than guessing at a date or a calendar."""
    found = _SEMVER.match((version or "").strip())
    bump = bump_of(subjects)
    if not found or not bump:
        return ""
    major, minor, patch = int(found["major"]), int(found["minor"]), int(found["patch"])
    if bump == "major":
        major, minor, patch = major + 1, 0, 0
    elif bump == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{found['prefix']}{major}.{minor}.{patch}"


def train_of(node: dict) -> tuple[dict, str]:
    """A repo's train from the host's read of it (``_TRAIN_QUERY``): the checks on the
    default branch's head, the last tag as its version, and the tail past that tag as what
    the train would cut next. Returns the train and the reason ``unreleased`` could not be
    derived, empty when it could, so the caller names the gap rather than letting a train
    with no next version pass for a shipped one."""
    head = (node.get("defaultBranchRef") or {}).get("target") or {}
    rollup = head.get("statusCheckRollup")
    train = {"checks": checks_of([rollup] if rollup else []), "version": "", "healthy": None, "deployed": ""}
    tag = (node.get("latestRelease") or {}).get("tag") or next(
        iter(((node.get("refs") or {}).get("nodes") or [])), None
    )
    if not tag:
        return train, "no tag to compare from"
    train["version"] = tag.get("name", "")
    compare = tag.get("compare") or {}
    train["unreleased_total"] = compare.get("aheadBy") or 0
    subjects = [c.get("messageHeadline", "") for c in (compare.get("commits") or {}).get("nodes") or [] if c]
    train["next_version"] = next_version_of(train["version"], subjects)
    if train["unreleased_total"] and not _SEMVER.match(train["version"]):
        return train, f"the tag {train['version']} is not semver, so what the tail would cut cannot be derived"
    return train, ""


# ---------------------------------------------------------------------------
# The pure derivation. This is what fixtures/ pins.
# ---------------------------------------------------------------------------


def _issue_stage(number: int, prs: list[dict]) -> tuple[str, str]:
    """Where a ticket sits in the loop right now, folded from its linked open PR, with the
    act that moves it - so a ticket already at a gate or awaiting a merge stops reading as
    plain untouched work."""
    for pr in prs:
        if not pr_resolves_ticket(pr.get("head", ""), pr.get("title", ""), pr.get("body", ""), number):
            continue
        if pr.get("checks") == CHECKS_RED:
            return "checks-red", "investigate"
        if pr.get("verdict") == VERDICT_PASS:
            return "awaiting-merge", "merge"
        if pr.get("verdict") == VERDICT_FAIL:
            # Section 5: a failing verdict goes back to resolve, and the reviewer's findings
            # are the work order. Its own state, not a fresh unreviewed PR's.
            return "changes-requested", "resolve"
        # Awaiting, and UNRECORDED with it: the third state is a completed review that
        # could not be recorded (section 5), so the ticket is at the gate, not back at
        # resolve. Same stage, same act - what it still needs is an independent reviewer.
        return "awaiting-review", "review"
    return "open", "resolve"


def _review_ticket(pr_number: int, position: dict) -> int | None:
    """The still-open ticket whose PR a live review targets, by the same branch-AND-text rule.
    None when that PR resolves no open ticket, an unlinked PR being its own concern.

    A run's label carries its ACT's target, and the two acts target different namespaces: a
    resolve's target is the ticket, a review's is the PR. Folding on the raw number therefore
    never matches for a review, which leaves the ticket showing an untouched row beside a
    running row whose number appears nowhere else in the queue."""
    pr = next((p for p in position.get("prs", []) if p.get("number") == pr_number), None)
    if pr is None:
        return None
    return next(
        (
            i.get("number")
            for i in position.get("issues", [])
            if pr_resolves_ticket(pr.get("head", ""), pr.get("title", ""), pr.get("body", ""), i.get("number"))
        ),
        None,
    )


def _row(repo, signal, detail, act, number=None, ts="", stage="", hidden=False) -> dict:
    return {
        "repo": repo, "signal": signal, "detail": detail, "act": act,
        "number": number, "ts": ts, "stage": stage, "hidden": hidden,
    }


def derive_inbox(
    positions: list[dict],
    archived: set[str] | None = None,
    running: list[dict] | None = None,
    hidden_repos: set[str] | None = None,
) -> list[dict]:
    """The queue (section 7). Pure: the same positions always derive the same rows.

    ``archived`` is the safety net for repos already dropped by the sweep: a tombstone's open
    issues are noise by definition, so one that slips through in a stale position stays out.

    ``hidden_repos`` carries the ``foundry-hidden`` TOPIC at repo scope, the twin of the
    label this derivation reads at ticket scope. Its rows are MARKED, never dropped: a repo
    held off the Foundry's surfaces is a deliberate choice, and a reader that can count what
    it is holding says so, where a reader handed a shortened queue cannot tell a choice from
    a loss. Supplied rather than discovered, for the same reason ``running`` is: the topic
    comes off a repo listing the derivation does not make.

    ``running`` is work in flight, one entry per concern
    (``{"repo": ..., "act": "resolve"|"review", "number": n}``). It is SUPPLIED, never
    discovered: its source differs by reader (a workflow engine, a desk's own live agents,
    nothing at all in a plain session), and a derivation that went looking for it would be
    inventing state rather than deriving it (section 6).
    """
    gone = {r.lower() for r in (archived or set())}
    held = {r.lower() for r in (hidden_repos or set())}
    rows: list[dict] = []
    for pos in positions or []:
        repo = pos.get("repo", "")
        if repo.lower() in gone or pos.get("archived"):
            continue
        issues = pos.get("issues", []) or []
        prs = pos.get("prs", []) or []
        train = pos.get("train", {}) or {}

        # --- Fold 1: a live run is THE row for the concern it works. ---
        working: set[int] = set()    # tickets a run works: their own rows fold into it
        reviewing: set[int] = set()  # PRs a review works: their own rows fold into it
        for job in running or []:
            if job.get("repo") != repo:
                continue
            act = job.get("act") or "resolve"
            num = job.get("number")
            ticket, what = num, f"#{num}"
            if act == "review" and num:
                reviewing.add(num)
                ticket = _review_ticket(num, pos)
                # Name the namespace each number lives in; a bare '#16' the rest of the queue
                # never mentions is unfindable.
                what = f"PR #{num}" + (f" for #{ticket}" if ticket else "")
            title = next((i.get("title", "") for i in issues if i.get("number") == ticket), "") if ticket else ""
            detail = (
                f"{act} {what} in progress" + (f": {title}" if title else "")
            ) if num else f"{act} in progress"
            rows.append(_row(repo, "running", detail, "watch", ticket, stage="in-progress"))
            if ticket:
                working.add(ticket)

        # --- Fold 2: a PR resolving a still-open ticket surfaces as that ticket's row. ---
        resolving = {
            pr.get("number")
            for pr in prs
            if any(
                pr_resolves_ticket(pr.get("head", ""), pr.get("title", ""), pr.get("body", ""), i.get("number"))
                for i in issues
            )
        }
        for pr in prs:
            number = pr.get("number")
            if number in resolving or number in reviewing:
                continue  # its ticket's row, or its own running row, already carries this concern
            title, ts = pr.get("title", ""), pr.get("updated_at", "")
            if pr.get("checks") == CHECKS_RED:
                rows.append(_row(repo, "red-ci", f"PR #{number} checks red: {title}", "investigate", number, ts))
            elif pr.get("verdict") == VERDICT_AWAITING:
                rows.append(_row(repo, "pr-review", f"PR #{number} awaits review: {title}", "review", number, ts))
            elif pr.get("verdict") == VERDICT_UNRECORDED:
                # Reviewed, unrecordably (section 5). Without this branch the PR raises no
                # row at all and drops out of the queue entirely - the reverse of what the
                # state means, which is that it is still waiting on a person.
                rows.append(_row(repo, "pr-review", f"PR #{number} awaits an independent reviewer: {title}", "review", number, ts))
            elif pr.get("verdict") == VERDICT_PASS:
                rows.append(_row(repo, "pr-review", f"PR #{number} passed review, awaits merge: {title}", "merge", number, ts))

        # A red default branch is the more urgent of the two red-CI producers: a PR's red
        # blocks one merge, the branch's red means what already merged is not shipping.
        if train.get("checks") == CHECKS_RED:
            at = f" at {train['version']}" if train.get("version") else ""
            rows.append(_row(repo, "red-ci", f"default branch is red{at}: what merged is not shipping", "investigate"))
        if train.get("healthy") is False:
            rows.append(_row(repo, "drift", f"deployment unhealthy at {train.get('deployed') or 'unknown revision'}", "investigate"))
        if train.get("next_version"):
            rows.append(_row(
                repo, "unreleased",
                f"{train.get('unreleased_total', 0)} unreleased commit(s); next would cut {train['next_version']}",
                "release",
            ))

        # Promotion (REF-Promotion.md section 6). A target that has not received the
        # proven release is work sitting unshipped, which is where `unreleased` already
        # sits, so it reads beside it. A target that CARRIES the release while the
        # signal it declared says nothing is not promotion work at all: it is a
        # deployment that does not answer, which this queue already calls drift, and
        # it keeps drift's urgency rather than inventing a second word for it.
        # Within the signal the rows carry no number to sort by, so they are emitted
        # in attention order here: a door someone else is sitting on outranks a release
        # that has simply not moved (REF-Promotion.md section 6).
        _PROMOTION_ATTENTION = {"unproven": 0, "unreadable": 1, "in-flight": 2, "pending": 3}
        for target in sorted(
            pos.get("promotion", []) or [],
            key=lambda t: (_PROMOTION_ATTENTION.get(t.get("state", ""), 9), t.get("target", "")),
        ):
            state = target.get("state", "")
            where = target.get("destination") or target.get("target", "")
            if state == "unproven":
                rows.append(_row(
                    repo, "drift",
                    f"{where} serves {target.get('accepted', '')} and does not answer",
                    "investigate", stage=state,
                ))
            elif state == "in-flight":
                rows.append(_row(
                    repo, "promotion",
                    f"{where}: {target.get('door_ref', 'a door')} awaits their review",
                    "watch", stage=state,
                ))
            elif state == "pending":
                rows.append(_row(
                    repo, "promotion",
                    f"{where} carries {target.get('accepted') or 'nothing'}, "
                    f"{target.get('proven', '')} is proven",
                    "promote", stage=state,
                ))
            elif state == "unreadable":
                rows.append(_row(
                    repo, "promotion",
                    f"{where} could not be read", "investigate", stage=state,
                ))

        for issue in issues:
            number = issue.get("number")
            if number in working:
                continue  # its running row above already carries this concern
            stage, act = _issue_stage(number, prs)
            rows.append(_row(
                repo, "issue", f"#{number} {issue.get('title', '')}", act, number,
                ts=issue.get("created_at", ""), stage=stage,
                hidden=HIDDEN_LABEL in [str(lb).lower() for lb in issue.get("labels", [])],
            ))

    # The hide at repo scope, applied to every signal rather than to tickets alone: a repo
    # off the surfaces took its red CI, its drift and its unshipped releases with it. Marked
    # here, at the end, precisely because it is not per-signal - a rule that had to be
    # remembered at each append site is a rule that would be forgotten at one.
    for row in rows:
        if row["repo"].lower() in held:
            row["hidden"] = True

    rows.sort(key=lambda r: (URGENCY.get(r["signal"], 9), r["repo"], r["number"] or 0))
    return rows


# ---------------------------------------------------------------------------
# The reads. Replaceable: a caller holding positions already calls the pure layer.
# ---------------------------------------------------------------------------


def _gh(*args: str) -> str:
    done = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout or "").strip()[:300])
    return done.stdout


def _gh_json(*args: str):
    return json.loads(_gh(*args) or "null")


def _graphql(query: str, **variables: str) -> dict:
    """One GraphQL read, its ``data`` kept even when part of it errored. ``gh api`` exits
    non-zero whenever the response carries an ``errors`` list, and the train is read twenty
    repos to a call: one repository the token cannot see must not take its nineteen
    neighbours down with it, so the body is parsed off stdout regardless of the exit code,
    and only a body with no ``data`` at all is a failed read."""
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for name, value in variables.items():
        args += ["-f", f"{name}={value}"]
    done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    try:
        body = json.loads(done.stdout or "null")
    except json.JSONDecodeError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise RuntimeError((done.stderr or done.stdout or "").strip()[:300])
    return body


#: A page of open PRs with everything the derivation needs: the branch and body for the link
#: rule, the rollup for checks, the PR's author and its reviews (each with its author and
#: association) for the verdict. ``first: 100`` is the API's own ceiling for one page, and
#: ``issueCount`` comes back beside it so a scope larger than the page is REPORTED rather
#: than silently trimmed to the part that fitted.
_PR_QUERY = (
    "query($q:String!){search(query:$q,type:ISSUE,first:100){issueCount nodes{... on PullRequest{"
    "number title repository{nameWithOwner} isDraft headRefName body updatedAt author{login} "
    "statusCheckRollup{state} reviews(last:20){nodes{state body author{login} authorAssociation}}}}}}"
)

#: One repo's train in one shape, read for every live repo in scope: the checks on the
#: default branch's head, the tag its last release cut (or, for a repo that tags without
#: releases, its newest tag), and that tag compared against ``HEAD``, which the host
#: resolves to the default branch, with the subjects of the tail past it. ``first: 100``
#: subjects bound the payload; the tail's LENGTH is ``aheadBy`` and is exact regardless.
_TRAIN_QUERY = (
    'fragment tail on Ref{name compare(headRef:"HEAD"){aheadBy commits(first:100){nodes{messageHeadline}}}} '
    "fragment train on Repository{nameWithOwner "
    "defaultBranchRef{name target{... on Commit{statusCheckRollup{state}}}} "
    "latestRelease{tag{...tail}} "
    'refs(refPrefix:"refs/tags/",first:1,orderBy:{field:TAG_COMMIT_DATE,direction:DESC}){nodes{...tail}}}'
)
#: Repos per train call: a floor of sixty repos costs three, and each response stays far
#: under the host's node ceiling.
_TRAIN_BATCH = 20


def _scope_repos(scope: str, repos: list[str]) -> tuple[list[str], set[str], set[str], list[str]]:
    """The repos in scope, the archived and the hidden among them read as their own facts,
    and what went unanswered.

    Both exclusions come off the ONE listing this already makes: ``isArchived`` and
    ``repositoryTopics`` are two more fields on a page the sweep pays for anyway, so neither
    fact costs a round trip and neither can disagree with the repo list it was read beside.

    An org is listed once with its archived flag and both facts come off that page: the live
    repos are what the train is read for, the archived ones are what the derivation excludes.
    Nothing filters tombstones out of a search instead: ``archived:`` is a REPOSITORY-search
    qualifier, inert inside a GraphQL issue search and, passed to ``gh search issues`` as raw
    query text, destructive - it is read as a search term and takes the scope down with it,
    so the sweep answers with issues from repositories nobody asked about. Explicitly named
    repos are an explicit choice; nothing is second-guessed.
    """
    if not scope:
        return list(repos), set(), set(), []
    try:
        listed = _gh_json(
            "repo", "list", scope, "--limit", "500",
            "--json", "nameWithOwner,isArchived,repositoryTopics",
        ) or []
    except RuntimeError as exc:
        return [], set(), set(), [
            f"red-ci (default branch), unreleased: the repos of {scope} could not be listed, "
            f"so no train was read and tombstones may appear: {exc}"
        ]
    unchecked: list[str] = []
    if len(listed) == 500:
        unchecked.append(
            "red-ci (default branch), unreleased: the 500-repo page filled, so the repos past it have no train read"
        )
    live = [r.get("nameWithOwner", "") for r in listed if not r.get("isArchived")]
    gone = {r.get("nameWithOwner", "") for r in listed if r.get("isArchived")}
    held = {
        r.get("nameWithOwner", "")
        for r in listed
        if HIDDEN_LABEL in _topics_of(r)
    }
    return live, gone, held, unchecked


def _topics_of(repo: dict) -> set[str]:
    """One repo listing's topics, lowercased. ``gh`` answers ``null`` for a repo carrying
    none and a list of ``{"name": ...}`` objects otherwise; a plain list of strings is
    accepted too, so a gh whose shape differs degrades to reading no topic rather than
    raising in the middle of a sweep."""
    return {
        (t.get("name", "") if isinstance(t, dict) else str(t)).lower()
        for t in (repo.get("repositoryTopics") or [])
    }


def _trains(repos: list[str]) -> tuple[dict[str, dict], list[str]]:
    """Each live repo's train, twenty repos to a call, and every read that went unanswered
    named by the signals it lost. A tail that could not be counted is grouped by its reason,
    so an org of untagged repos costs the reader one line rather than one per repo."""
    trains: dict[str, dict] = {}
    unchecked: list[str] = []
    uncounted: dict[str, list[str]] = {}
    for start in range(0, len(repos), _TRAIN_BATCH):
        batch = repos[start:start + _TRAIN_BATCH]
        fields = " ".join(
            f"r{i}: repository(owner:{json.dumps(owner)},name:{json.dumps(name)}){{...train}}"
            for i, (owner, _, name) in enumerate(r.partition("/") for r in batch)
        )
        try:
            data = _graphql(f"query{{{fields}}} {_TRAIN_QUERY}")["data"]
        except RuntimeError as exc:
            unchecked.append(f"red-ci (default branch), unreleased for {', '.join(batch)}: {exc}")
            continue
        for i, repo in enumerate(batch):
            node = data.get(f"r{i}")
            if not node:
                unchecked.append(f"red-ci (default branch), unreleased for {repo}: the repository could not be read")
                continue
            train, gap = train_of(node)
            trains[node.get("nameWithOwner") or repo] = train
            if gap:
                uncounted.setdefault(gap, []).append(repo)
    for gap, named in uncounted.items():
        unchecked.append(f"unreleased for {', '.join(named)}: {gap}")
    return trains, unchecked


def _scope_positions(scope: str, repos: list[str]) -> tuple[list[dict], set[str], set[str], list[str]]:
    """Positions for a scope, the archived and hidden repos to exclude, and what went unanswered.

    One listing and one search per signal cover the whole account and the trains ride twenty
    repos to a call, so a floor of sixty repos costs six calls rather than sixty. Every
    signal the derivation can raise is read here or named in ``unchecked`` with its reason
    (section 7): an absent row and a healthy row look identical on the surface, and a silent
    gap reads as "nothing needs me".
    """
    where = ["--owner", scope] if scope else [arg for r in repos for arg in ("--repo", r)]
    qualifier = f"org:{scope}" if scope else " ".join(f"repo:{r}" for r in repos)
    live, gone, held, unchecked = _scope_repos(scope, repos)
    by_repo: dict[str, dict] = {}

    def position(repo: str) -> dict:
        return by_repo.setdefault(repo, {"repo": repo, "issues": [], "prs": [], "train": {}})

    try:
        found = _gh_json(
            "search", "issues", "--state", "open", "--limit", "200",
            "--json", "number,title,repository,labels,createdAt", *where,
        ) or []
        if len(found) == 200:
            unchecked.append("issue: the 200-item page filled, so the backlog is longer than this queue")
        for issue in found:
            repo = (issue.get("repository") or {}).get("nameWithOwner", "")
            position(repo)["issues"].append({
                "number": issue.get("number"),
                "title": issue.get("title", ""),
                "labels": [lb.get("name", "") for lb in issue.get("labels") or []],
                "created_at": issue.get("createdAt", ""),
            })
    except RuntimeError as exc:
        unchecked.append(f"issue: {exc}")

    try:
        search = _graphql(_PR_QUERY, q=f"{qualifier} is:open is:pr")["data"].get("search") or {}
        nodes = [n for n in (search.get("nodes") or []) if n]
        if (search.get("issueCount") or 0) > len(nodes):
            unchecked.append(
                f"pr-review, red-ci: {search['issueCount']} open PRs in scope, {len(nodes)} read - the rest are not in this queue"
            )
        for node in nodes:
            repo = (node.get("repository") or {}).get("nameWithOwner", "")
            position(repo)["prs"].append({
                "number": node.get("number"),
                "title": node.get("title", ""),
                "head": node.get("headRefName", ""),
                "body": node.get("body") or "",
                "draft": bool(node.get("isDraft")),
                "updated_at": node.get("updatedAt", ""),
                "checks": checks_of([node["statusCheckRollup"]] if node.get("statusCheckRollup") else []),
                "verdict": verdict_of(
                    (node.get("reviews") or {}).get("nodes", []),
                    (node.get("author") or {}).get("login", ""),
                ),
            })
    except RuntimeError as exc:
        unchecked.append(f"pr-review, red-ci (pull requests): {exc}")

    # The train is read for every live repo, not only the ones a search mentioned: a quiet
    # repo's default branch can be red and its tail unshipped all the same.
    trains, gaps = _trains(live)
    for repo, train in trains.items():
        position(repo)["train"] = train
    unchecked.extend(gaps)

    # No cluster CLI is shelled here, so deployment health is never inferred: an absent row
    # and a healthy row look identical, and a silent gap reads as "nothing needs me".
    unchecked.append("drift: no cluster reader is wired into this sweep")
    # No promotion contract is read here either, so no position carries a `promotion` list;
    # the signal is declared rather than left to read as "nothing to promote".
    unchecked.append("promotion: no promotion contract is read by this sweep")
    return list(by_repo.values()), gone, held, unchecked


def _parse_running(raw: str | None) -> list[dict]:
    """``<owner/name>:<act>:<number>`` entries, comma separated."""
    jobs: list[dict] = []
    for entry in (raw or "").split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3 and parts[2].isdigit():
            jobs.append({"repo": parts[0], "act": parts[1], "number": int(parts[2])})
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive the maintenance inbox for a scope.")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--org", help="every repo the account owns")
    scope.add_argument("--repos", help="comma-separated owner/name list")
    parser.add_argument("--running", help="work in flight: <owner/name>:<act>:<number>,...")
    parser.add_argument("--json", action="store_true", help="print the queue as data")
    parser.add_argument(
        "--show-hidden", action="store_true",
        help="include the foundry-hidden rows the report otherwise only counts",
    )
    args = parser.parse_args()

    repos = [r.strip() for r in (args.repos or "").split(",") if r.strip()]
    positions, gone, held, unchecked = _scope_positions(args.org, repos)
    queue = derive_inbox(
        positions, archived=gone, running=_parse_running(args.running), hidden_repos=held,
    )

    # The data carries every row, marked. Holding one back is a READER's act (section 7),
    # and a consumer of --json is a reader that has not decided yet: shortening the queue
    # here would take that decision away from it and lose the mark that informs it.
    if args.json:
        print(json.dumps({"queue": queue, "unchecked": unchecked}, indent=2))
        return 0

    shown = queue if args.show_hidden else [row for row in queue if not row["hidden"]]
    if not shown:
        print("The queue is empty: nothing in this scope needs attention.")
    for row in shown:
        stage = f" [{row['stage']}]" if row["stage"] else ""
        mark = "*" if row["hidden"] else " "
        print(f"{mark}{row['signal']:<10} {row['repo']:<40}{stage:<18} {row['detail']}  -> {row['act']}")
    # Say what is being held, never just hold it: an exclusion nobody can see is
    # indistinguishable from a signal nobody raised.
    if (n := len(queue) - len(shown)):
        print(f"HELD BACK  {n} row(s) marked foundry-hidden; --show-hidden to see them")
    for gap in unchecked:
        print(f"UNCHECKED  {gap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
