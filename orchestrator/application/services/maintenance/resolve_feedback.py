"""Maintenance shared orchestration over explicit contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.maintenance_resolver import pr_resolves_ticket
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.services.maintenance.merger import helper_merger
from orchestrator.application.services.maintenance.verdict import decide
from orchestrator.domain.maintenance import VERDICT_FAIL
from orchestrator.domain.services.repository_door import home_pr_from_comments


def helper_resolve_feedback(
    repo: str,
    ticket: int | None,
    *,
    door: Door | None,
    msource: MaintenanceSource | None,
    psource: PromotionSource | None,
    cap_git_roles: GitRolesPort,
    cap_instantiation: InstantiationPort,
    cap_list_git_identities: ListGitIdentitiesPort,
    home,
) -> str:
    """When re-driving a resolve over a PR a fresh-eyes review already FAILed, the body of
    the review that decided the FAIL is the work order (REF-Maintenance section 5): thread it so the worker
    REVISES the open PR instead of opening a second one for the same ticket (one ticket =
    one PR). The operator-pressed twin of the one-shot engine's re-drive (_redrive_oneshot).

    Empty when there is no open PR for the ticket or its verdict is not FAIL - a first
    resolve, or a re-drive over a still-awaiting or passing PR - so the worker gets the
    fresh 'open the PR' prompt. Source failures remain explicit."""
    if msource is None or not ticket:
        return ""
    if home is not None:
        if door is None:
            from orchestrator.domain.exceptions.source_unavailable import (
                SourceUnavailable,
            )

            raise SourceUnavailable("repository home review source is unavailable")
        pointer = home_pr_from_comments(msource.issue_comments(repo, ticket))
        if pointer is None:
            return ""
        pr = door.pull_request(pointer[0], pointer[1], home.credential)
        if not pr or (pr.state or "").lower() != "open":
            return ""
        reviews = pr.reviews or []
        merger = ""
    else:
        pr = next(
            (
                p
                for p in msource.open_prs(repo)
                if pr_resolves_ticket(
                    p.head_branch or "", p.title, p.body or "", ticket
                )
            ),
            None,
        )
        if pr is None:
            return ""
        reviews = msource.pr_reviews(repo, pr.number)
        merger = partial(
            helper_merger,
            cap_git_roles=cap_git_roles,
            cap_list_git_identities=cap_list_git_identities,
        )()
    author = pr.author or ""
    verdict, findings = decide(reviews, author, merger)
    return findings if verdict == VERDICT_FAIL else ""
