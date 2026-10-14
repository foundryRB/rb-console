"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from functools import partial

from orchestrator.application.maintenance_resolver import (
    derive_positions,
    pr_resolves_ticket,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.services.identity.agent_slug import helper_agent_slug
from orchestrator.application.services.settings.shared_identities import (
    helper_shared_identities,
)
from orchestrator.domain.model.maintenance_check import MaintenanceCheck
from orchestrator.domain.model.maintenance_issue import MaintenanceIssue
from orchestrator.domain.model.maintenance_positions import MaintenancePositions
from orchestrator.domain.model.maintenance_pull_request import MaintenancePullRequest
from orchestrator.domain.model.maintenance_review import MaintenanceReview
from orchestrator.domain.model.promotion_target import PromotionTarget
from orchestrator.domain.services.repository_door import home_pr_from_comments


def helper_managed_positions(
    repo: str,
    issues: Sequence[MaintenanceIssue],
    home: PromotionTarget,
    *,
    door: Door | None,
    msource: MaintenanceSource | None,
    cap_git_roles: GitRolesPort,
    cap_list_git_identities: ListGitIdentitiesPort,
) -> MaintenancePositions:
    """The loop of an app whose home we do not own: our tickets, each followed to the ONE
    home pull request it points at, and no train.

    The pointer is the marked comment the resolve worker leaves on our ticket. A ticket
    with no pointer has no PR as far as the loop can see, which is the honest reading of
    a resolve that has not landed; a pointer whose PR cannot be read (the credential not
    held, the PR gone) reads the same way, never as resolved. The home PR is handed to the
    derivation in the shape it already understands - open PRs with their reviews and
    checks, closed PRs as the lightweight terminal record - so the positions, the
    lifecycle strip and the one-shot judge derive a Managed ticket by the SAME rules as
    any other; only the source of the PR differs.

    Reading follows the pointer and only the pointer: the home's PR list is never
    listed, so a Managed ticket costs the pair one PR's reads however many PRs they have.
    """
    src = msource
    assert src is not None
    prs: list[MaintenancePullRequest] = []
    closed: list[MaintenancePullRequest] = []
    reviews: dict[int, tuple[MaintenanceReview, ...]] = {}
    checks: dict[int, tuple[MaintenanceCheck, ...]] = {}
    can_read = door is not None and src is not None
    for issue in issues:
        if issue.is_pull_request:
            continue
        number = issue.number
        pointer = (
            home_pr_from_comments(src.issue_comments(repo, number))
            if can_read
            else None
        )
        if pointer is None:
            continue
        home_repo, pr_number = pointer
        pr = (
            door.pull_request(home_repo, pr_number, home.credential)
            if can_read
            else None
        )
        if not pr:
            continue
        if not pr_resolves_ticket(pr.head_branch, pr.title, pr.body, number):
            pr = replace(
                pr,
                head_branch=f"home/{number}-{helper_agent_slug(pr.title) or 'pr'}",
                body=f"{pr.body}\n\n(resolves {repo}#{number})",
            )
        if (pr.state or "").lower() == "open":
            prs.append(pr)
            reviews[pr_number] = pr.reviews
            checks[pr_number] = pr.checks
        else:
            closed.append(pr)
    return derive_positions(
        repo,
        issues,
        prs,
        reviews,
        checks,
        [],
        [],
        git_user=partial(
            helper_shared_identities,
            cap_git_roles=cap_git_roles,
            cap_list_git_identities=cap_list_git_identities,
        )(),
        deployed="",
        healthy=None,
        closed_prs=closed,
        default_checks=[],
    )
