"""Merge only the freshly reviewed head, under the caller's durable grant."""

from __future__ import annotations

from orchestrator.application.events import PR_MERGED, state_fact
from orchestrator.application.maintenance_resolver import checks_state
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.maintenance_acts import MaintenanceActs
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.services.maintenance.merger import helper_merger
from orchestrator.application.services.maintenance.verdict import decide
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.promotion.home_target import helper_home_target
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.maintenance import CHECKS_GREEN, VERDICT_PASS
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.pull_merge_result import PullMergeResult


class MaintenanceMerge:
    def __init__(
        self,
        *,
        events: EventPublisher | None,
        macts: MaintenanceActs | None,
        msource: MaintenanceSource | None,
        psource: PromotionSource | None,
        cap_instantiation: InstantiationPort,
        cap_git_roles: GitRolesPort,
        cap_list_git_identities: ListGitIdentitiesPort,
        admission: OperationAdmission,
    ) -> None:
        self.events, self.macts, self.msource, self.psource = (
            events,
            macts,
            msource,
            psource,
        )
        self.cap_instantiation, self.cap_git_roles = cap_instantiation, cap_git_roles
        self.cap_list_git_identities, self.admission = (
            cap_list_git_identities,
            admission,
        )

    def _validate(self, repo: str, number: int, expected_revision: str | None) -> str:
        if self.macts is None or self.msource is None:
            raise SourceUnavailable(
                "Fresh repository evidence and a mutation door are required"
            )
        home = helper_home_target(
            repo, psource=self.psource, cap_instantiation=self.cap_instantiation
        )
        if home is not None:
            raise Conflict("The repository home owns the merge")
        pr = self.msource.pr(repo, number)
        if not pr or str(pr.state or "").lower() != "open":
            raise Conflict("The pull request is not open")
        head = str(pr.head_sha or "")
        if not head:
            raise SourceUnavailable("The pull request head could not be observed")
        if expected_revision and expected_revision.strip('"') != head:
            raise Conflict("The pull request head changed")
        merger = helper_merger(
            cap_git_roles=self.cap_git_roles,
            cap_list_git_identities=self.cap_list_git_identities,
        )
        verdict, _ = decide(
            self.msource.pr_reviews(repo, number),
            str(pr.author or ""),
            merger,
        )
        if (
            verdict != VERDICT_PASS
            or checks_state(self.msource.check_runs(repo, head)) != CHECKS_GREEN
        ):
            raise Conflict("A current independent PASS and green checks are required")
        return head

    def execute(
        self,
        repo: str,
        number: int,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> PullMergeResult:
        context.authorize("maintenance.merge", repo)
        prepared: list[str] = []

        def validate() -> None:
            prepared.append(self._validate(repo, number, expected_revision))

        def dispatch() -> dict:
            merged = self.macts.merge(repo, number, expected_head=prepared[0])
            if not merged.merged:
                raise Conflict(merged.message or "The repository host refused the merge")
            state_fact(
                self.events,
                event_type=PR_MERGED,
                subject=repo,
                data={
                    "repo": repo,
                    "pr": number,
                    "head": prepared[0],
                    "by": "operator",
                },
            )
            return safe_value(merged)

        retained = self.admission.execute(
            context,
            "maintenance.merge",
            repo,
            operation_id,
            {"number": number, "expected_revision": expected_revision},
            dispatch,
            validate=validate,
        )

        return restore_result(retained, PullMergeResult)
