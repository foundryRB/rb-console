"""MaintenanceSubstance over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.maintenance_modes import is_contributor
from orchestrator.application.maintenance_resolver import checks_state
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.maintenance.deployed_of import helper_deployed_of
from orchestrator.application.services.maintenance.merger import helper_merger
from orchestrator.application.services.maintenance.verdict import derive_verdict
from orchestrator.application.services.settings.shared_identities import (
    helper_shared_identities,
)
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable


class MaintenanceSubstance:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        msource: MaintenanceSource | None,
        workflows: WorkflowRunner | None,
        cap_git_roles: GitRolesPort,
        cap_list_git_identities: ListGitIdentitiesPort,
    ) -> None:
        self.observations = observations
        self.msource = msource
        self.workflows = workflows
        self.cap_git_roles = cap_git_roles
        self.cap_list_git_identities = cap_list_git_identities

    def execute(self, repo: str, kind: str, id: int | None = None) -> dict:
        """The selected item's native content (INT-FC-R62/R63): the issue body, the PR
        with its ACTUAL diff (files + patch text), the docs signals, or the releases.
        A link out is not substance; only an unreachable API degrades the pane to it."""
        if self.msource is None:
            return {"kind": kind}
        src = self.msource
        if kind == "issue" and id:
            data = src.issue(repo, id)
            return {
                "kind": "issue",
                "number": data.number,
                "title": data.title,
                "author": data.author or "",
                "labels": list(data.labels),
                "body": data.body or "",
                "url": data.url,
            }
        if kind == "pr" and id:
            data = src.pr(repo, id)
            author = data.author or ""
            reviews = src.pr_reviews(repo, id)
            return {
                "kind": "pr",
                "number": data.number,
                "title": data.title,
                "author": author,
                "head": data.head_branch or "",
                "body": data.body or "",
                "url": data.url,
                "verdict": derive_verdict(
                    reviews,
                    author,
                    partial(
                        helper_merger,
                        cap_git_roles=self.cap_git_roles,
                        cap_list_git_identities=self.cap_list_git_identities,
                    )(),
                ),
                "checks": checks_state(src.check_runs(repo, data.head_sha or "")),
                "contributor": is_contributor(
                    author,
                    partial(
                        helper_shared_identities,
                        cap_git_roles=self.cap_git_roles,
                        cap_list_git_identities=self.cap_list_git_identities,
                    )(),
                ),
                "files": [
                    {
                        "filename": f.filename,
                        "status": f.status,
                        "additions": f.additions,
                        "deletions": f.deletions,
                        "patch": f.patch,
                    }
                    for f in src.pr_files(repo, id)
                ],
                "reviews": [
                    {
                        "author": r.author or "",
                        "submitted_at": r.submitted_at,
                        "body": r.body or "",
                    }
                    for r in reviews
                ],
            }
        if kind == "docs":
            issues = [
                i
                for i in src.open_issues(repo)
                if not i.is_pull_request
                and any("doc" in label.lower() for label in i.labels)
            ]
            log = ""
            if self.workflows is not None:
                try:
                    mine = [
                        r
                        for r in self.workflows.list_runs()
                        if r.repository == repo
                        and r.kind == "maintenance"
                        and r.maintenance_act == "reconcile-docs"
                    ]
                    if mine:
                        log = self.workflows.logs(mine[0].handle, 120)
                except (OSError, SourceUnavailable):
                    log = ""
            return {
                "kind": "docs",
                "issues": [
                    {
                        "number": i.number,
                        "title": i.title,
                        "url": i.url,
                    }
                    for i in issues
                ],
                "log": log,
            }
        if kind == "releases":
            deployed, healthy = partial(
                helper_deployed_of, observations=self.observations
            )(repo)
            return {
                "kind": "releases",
                "releases": [
                    {
                        "tag": release.tag,
                        "name": release.name,
                        "published_at": release.published_at,
                        "url": release.url,
                    }
                    for release in src.releases(repo)
                ],
                "deployed": deployed,
                "healthy": healthy,
            }
        return {"kind": kind}
