"""MaintenancePositions over consumed application contracts."""

from __future__ import annotations

from functools import partial

from orchestrator.application.maintenance_resolver import derive_positions
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.services.maintenance.deployed_of import helper_deployed_of
from orchestrator.application.services.maintenance.managed_positions import (
    helper_managed_positions,
)
from orchestrator.application.services.maintenance.merger import helper_merger
from orchestrator.application.services.promotion.home_target import helper_home_target
from orchestrator.application.services.settings.shared_identities import (
    helper_shared_identities,
)
from orchestrator.domain.model.maintenance_positions import (
    MaintenancePositions as DomainMaintenancePositions,
)


class MaintenancePositions:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        door: Door | None,
        msource: MaintenanceSource | None,
        psource: PromotionSource | None,
        cap_git_roles: GitRolesPort,
        cap_instantiation: InstantiationPort,
        cap_list_git_identities: ListGitIdentitiesPort,
    ) -> None:
        self.observations = observations
        self.door = door
        self.msource = msource
        self.psource = psource
        self.cap_git_roles = cap_git_roles
        self.cap_instantiation = cap_instantiation
        self.cap_list_git_identities = cap_list_git_identities

    def execute(self, repo: str) -> DomainMaintenancePositions:
        """One repo's loop positions, derived on read (INT-FC-R58): issues are intent,
        PRs are review (verdict + checks per PR), the train is shipping.

        A MANAGED app's loop reads differently in exactly one way (foundry-platform#136):
        its tickets are ours, its pull requests are on a home we do not own, and we release
        nothing. So its PRs are not listed from anywhere - each ticket carries a recorded
        pointer to the one PR its resolve opened on the home, and that PR is read on the
        pair's credential. And it has no release train at all: not ours (there is nothing to
        release) and not theirs (their versioning is theirs, in whatever scheme, and syncing
        to it would be a permanent source of drift). An empty train feeds the inbox nothing
        to say about releases, which is the truth."""
        if self.msource is None:
            return DomainMaintenancePositions(repo=repo)
        src = self.msource
        issues = src.open_issues(repo)
        home = partial(
            helper_home_target,
            psource=self.psource,
            cap_instantiation=self.cap_instantiation,
        )(repo)
        if home is not None:
            return partial(
                helper_managed_positions,
                door=self.door,
                msource=self.msource,
                cap_git_roles=self.cap_git_roles,
                cap_list_git_identities=self.cap_list_git_identities,
            )(repo, issues, home)
        prs = src.open_prs(repo)
        reviews = {p.number: src.pr_reviews(repo, p.number) for p in prs}
        checks = {p.number: src.check_runs(repo, p.head_sha or "") for p in prs}
        deployed, healthy = partial(helper_deployed_of, observations=self.observations)(
            repo
        )
        closed = src.closed_prs(repo)
        default_checks = src.default_branch_checks(repo)
        return derive_positions(
            repo,
            issues,
            prs,
            reviews,
            checks,
            src.tags(repo),
            src.unreleased_subjects(repo),
            git_user=partial(
                helper_shared_identities,
                cap_git_roles=self.cap_git_roles,
                cap_list_git_identities=self.cap_list_git_identities,
            )(),
            merger=partial(
                helper_merger,
                cap_git_roles=self.cap_git_roles,
                cap_list_git_identities=self.cap_list_git_identities,
            )(),
            deployed=deployed,
            healthy=healthy,
            closed_prs=closed,
            default_checks=default_checks,
        )
