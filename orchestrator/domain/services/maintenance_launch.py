"""Compile a maintenance drive into an Argo Workflow (INT-FC-R67). Pure, like the
delivery compiler, and built on the SAME worker template (credential by ref, explicit
container command, bounded retries and deadline), so the launch guards INT-FC-R25 and
INT-FC-R48 hold here by construction. Workers read skills from their pinned playbook tree.

A maintenance worker leaves no ``.delivery/`` record and closes no gate, so the
template's record and gate slots ride empty - the entrypoint then skips record
validation and the one-shot stamp block entirely. Merging is NEVER compiled into a
worker: one-shot's merge is the engine's act after the run, over the recorded verdict
(INT-FC-R65).
"""
from __future__ import annotations

from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.pair_home import PairHome
from orchestrator.domain.services.delivery_launch import (
    HEADLESS_TURN,
    pinned_skill_instruction,
)

_API = "argoproj.io/v1alpha1"
# No baked worker image: the maintenance compiler takes the install-supplied ``worker_image``
# its caller resolved (FC_WORKER_IMAGE at the composition root, no default), the SAME value the
# delivery compiler gets, so the two launches share one owner-free definition instead of each
# hardcoding the org's registry path (REF-AppContract section 1).

#: The three drive-able acts and the skill each runs. The console renders and drives
#: exactly what the skills do by hand; there is no fourth act to invent.
ACT_SKILLS = {
    "resolve": "resolve-ticket",
    "review": "review-pr",
    "reconcile-docs": "reconcile-docs",
}

#: WHO runs each act: the playbook catalog agent the Console hands it to. The Programmer
#: works the loop's two hands-on acts; the Reviewer is the outsider, and it being a DIFFERENT
#: agent than the Programmer is what keys the two to different git identities, so a driven
#: review can approve a driven PR (decision 0001).
ACT_AGENTS = {
    "resolve": "programmer",
    "review": "reviewer",
    "reconcile-docs": "programmer",
}

_NEVER = (
    "Never merge any PR, never close any issue by hand, and never sign anything: "
    "the verdict gate's merge is the operator's act (gated) or the engine's over a "
    "recorded PASS (one-shot), and the closing keyword closes tickets."
)
#: How every driven review ends: on one of review-pr's three verdicts. UNRECORDED is the
#: one a reviewer whose identity is the PR's author or the merger owes (REF-Maintenance
#: section 5), so a console with one git identity still ends its review as the skill does.
_VERDICT_ENDING = (
    "post your findings as a PR review whose LAST line is one of the review-pr skill's "
    "three verdicts: `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: UNRECORDED` when your "
    "identity is the PR's author or the merger and so can record neither. "
)

#: A headless resolve lands its commit and pull request within its single turn (INT-FC-R158).
_NO_PARK = (
    f" Land your work BEFORE this run ends: {HEADLESS_TURN} - run any generation to completion "
    "in the foreground, or commit it incrementally. The commit (and, in a PR mode, the open PR) "
    "must actually exist when you stop, or the run has failed."
)
#: The PR modes' escape hatch, so "too big to finish" is a draft PR, never an empty run.
_DRAFT_FALLBACK = (
    " If the ticket is too large to finish in one run, still open a DRAFT PR with what you "
    "have and note what remains in the body - never end the run with nothing pushed."
)
def home_directive(home: PairHome | None, repo: str) -> str:
    """What an act over a foreign home must be told, and nothing more.

    The agent lands in a clone of THEIR repository with our ticket's number in hand, which is
    a shape no skill can infer from the tree it wakes up in: without being told, it would look
    for the ticket where it is standing (their tracker, or nothing) and open its pull request
    against whatever remote it found. Both coordinates are stated, and the one rule that
    follows from not owning the place - the merge is theirs, and their repo is not ours to
    reshape - is stated with them.
    """
    if home is None:
        return ""
    return (
        f" IMPORTANT - this app's home is {home.repo}, which the foundry does NOT own. You are "
        f"in a clone of THEIR repository, on {home.branch}. The ticket lives on OUR repo "
        f"({repo}) and is read there; your branch and your pull request go to THEIRS, against "
        f"{home.branch}. Never merge it - the merge is theirs - and never add the foundry's own "
        "conformance, CI, or scaffolding to their repository: adoption changes nothing in a "
        "home we do not own. Work to THEIR conventions and their tests, which are what "
        "proven-in-CI means for this app."
        # TWO coordinates means two credentials, and the agent cannot see which is which.
        # GH_TOKEN is ours and reaches our org: right for the ticket, wrong for their repo,
        # which was never granted to it. Anything on their repository goes through the door
        # (foundry-platform#167), which carries the grant that pair gave us and their host.
        # Without being told, an agent runs plain `gh pr create` in a clone of their tree and
        # authenticates as us against a repository nobody granted us.
        f" Your git push to {home.repo} is already authenticated (a credential helper scoped "
        f"to that repository). For anything on {home.repo} that speaks to the API rather than "
        "to git - opening the pull request, reading it, reviewing it - run \"$FC_PAIR_DOOR\" "
        "in place of `gh`, with the same arguments (for example: \"$FC_PAIR_DOOR\" pr create "
        f"--repo {home.repo} ...). Plain `gh` carries OUR credential, which reaches our org "
        "and was never granted to theirs; it is still what you use for the ticket on "
        f"{repo}. Never print, echo, or copy the door's token."
    )


#: Maintenance workers use interaction=auto with no human channel inside the pod
#: (INT-FC-R39). Open decisions follow the skill's autonomous path.
_AUTO = (
    " You are running with interaction=auto: no human is reachable inside this pod. Never "
    "prompt or wait for a person; resolve every open decision autonomously - make the "
    "smallest reasonable call, record it in the PR body or the commit message, and continue."
)
#: Commit hygiene is part of every worker prompt. The shared build workflow requires
#: Conventional Commits without co-author or AI-attribution trailers.
_HYGIENE = (
    " Write every commit message with NO co-author or AI-attribution trailer of any kind: "
    "no Co-Authored-By line, no 'Generated with' line, no tool credit. CI rejects them and "
    "the branch ships nothing until a later commit clears the push range."
)


def _resolve_prompt(repo: str, ticket: int, mode: MaintenanceMode, feedback: str = "") -> str:
    base = (
        pinned_skill_instruction("resolve-ticket") + f"Run resolve-ticket for repo {repo}, "
        f"resolving ticket #{ticket} through the maintenance loop (REF-Maintenance). "
    )
    if mode is MaintenanceMode.DIRECT:
        return base + (
            "This drive is DIRECT mode: make the fix as a Conventional Commit on the "
            f"default branch referencing the ticket (#{ticket}) with the closing keyword "
            "in the body; no branch, no PR. Run the repo's conformance before committing. "
            + _NEVER + _NO_PARK
        )
    # A retry after a one-shot review FAIL: the branch and PR already exist, so the worker
    # REVISES them (the reviewer's findings are the work order, REF-Maintenance section 5)
    # rather than opening a second PR for one ticket (§2: one ticket = one PR).
    if feedback:
        return base + (
            f"A prior attempt already opened the PR for #{ticket}, and a fresh-eyes review "
            "returned VERDICT: FAIL. Do NOT open a new PR or a new branch: check out the "
            f"existing ticket branch for #{ticket}, address the review's findings in full, "
            "run the repo's conformance, and push to UPDATE the open PR. Keep "
            f"`Closes #{ticket}` in the resolving commit. The findings are the work order:"
            f"\n\n{feedback}\n\n" + _NEVER + _NO_PARK + _DRAFT_FALLBACK
        )
    return base + (
        f"Branch as {{type}}/{ticket}-{{slug}}, commit conventionally referencing "
        f"(#{ticket}) with `Closes #{ticket}` in the body, run the repo's conformance, "
        "and open the PR (title `type(#n): subject`). Stop when the PR is open. "
        + _NEVER + _NO_PARK + _DRAFT_FALLBACK
    )


def _review_prompt(repo: str, pr: int) -> str:
    return (
        pinned_skill_instruction("review-pr") + f"Run review-pr for repo {repo}, reviewing "
        f"PR #{pr} with fresh eyes: read the diff against the linked ticket, the routed "
        "REFs for the touched stack, and the CI evidence; " + _VERDICT_ENDING + _NEVER
    )


def _reconcile_prompt(repo: str) -> str:
    return (
        pinned_skill_instruction("reconcile-docs") + f"Run reconcile-docs for repo {repo}: audit "
        "docs/ against the code and REPORT every drift found, one line each, in your "
        "output. This is a check run: filing tickets is the operator's confirmed act, "
        "so file nothing and change nothing - the report is the deliverable. " + _NEVER
    )


def build_maintenance_prompt(
    act: str, repo: str, target: int | None, mode: MaintenanceMode, feedback: str = ""
) -> str:
    """The worker prompt for one maintenance act. ``target`` is the ticket (resolve)
    or PR number (review); reconcile-docs takes none. ``feedback`` (resolve only) turns
    the drive into a revision of the open PR on a prior review's FAIL findings."""
    if act == "resolve":
        if not target:
            raise ValueError("resolve needs a ticket number")
        return _resolve_prompt(repo, target, mode, feedback)
    if act == "review":
        if not target:
            raise ValueError("review needs a PR number")
        return _review_prompt(repo, target)
    if act == "reconcile-docs":
        return _reconcile_prompt(repo)
    known = ", ".join(ACT_SKILLS)
    raise ValueError(f"unknown maintenance act {act!r}; one of: {known}")
