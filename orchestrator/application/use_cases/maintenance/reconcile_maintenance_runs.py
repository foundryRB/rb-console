"""Reconcile a delegated repository through an independent command entry point."""

from __future__ import annotations

from orchestrator.application.ports.inbound.maintenance.maintenance_merge import (
    MaintenanceMergePort,
)
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.runs.run_graph import RunGraphPort
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.inbound.settings.delivery_config import (
    DeliveryConfigPort,
)
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.list_git_identities import (
    ListGitIdentitiesPort,
)
from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.door import Door
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.execution.workflow_compiler import (
    WorkflowCompiler,
)
from orchestrator.application.ports.outbound.maintenance_source import MaintenanceSource
from orchestrator.application.ports.outbound.projections.observation_store import (
    ObservationStore,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.maintenance.judge_oneshot_runs import (
    helper_judge_oneshot_runs,
)
from orchestrator.application.services.operations.admitted_maintenance_acts import (
    AdmittedMaintenanceActs,
)
from orchestrator.application.services.operations.admitted_workflow_runner import (
    AdmittedWorkflowRunner,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.domain.delivery import same_repository
from orchestrator.domain.model.command_context import CommandContext


class ReconcileMaintenanceRuns:
    def __init__(
        self,
        *,
        observations: ObservationStore,
        config: ConfigStore | None,
        credentials: CredentialStore | None,
        door: Door | None,
        events: EventPublisher | None,
        msource: MaintenanceSource | None,
        psource: PromotionSource | None,
        studios: StudioGateway | None,
        worker_image: str,
        workflows: WorkflowRunner | None,
        cap_delivery_config: DeliveryConfigPort,
        cap_git_roles: GitRolesPort,
        cap_instantiation: InstantiationPort,
        cap_list_git_identities: ListGitIdentitiesPort,
        cap_pair_credential_held: PairCredentialHeldPort,
        cap_run_graph: RunGraphPort,
        cap_run_retention: RunRetentionPort,
        compiler: WorkflowCompiler,
        admission: OperationAdmission,
        authorization_revision: str,
        cap_maintenance_merge: MaintenanceMergePort,
    ) -> None:
        self.observations = observations
        self.config = config
        self.credentials = credentials
        self.door = door
        self.events = events
        self.msource = msource
        self.psource = psource
        self.studios = studios
        self.worker_image = worker_image
        self.workflows = workflows
        self.cap_delivery_config = cap_delivery_config
        self.cap_git_roles = cap_git_roles
        self.cap_instantiation = cap_instantiation
        self.cap_list_git_identities = cap_list_git_identities
        self.cap_pair_credential_held = cap_pair_credential_held
        self.cap_run_graph = cap_run_graph
        self.cap_run_retention = cap_run_retention
        self.compiler = compiler
        self.admission = admission
        self.authorization_revision = authorization_revision
        self.cap_maintenance_merge = cap_maintenance_merge

    def execute(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        context.authorize(
            "maintenance.reconcile",
            repo,
            current_authorization_revision=self.authorization_revision,
        )
        scoped = self.observations.scope(repo)
        rows = [
            row
            for row in self.observations.runs
            if same_repository(row.repository, context.repository_id(repo))
        ]

        macts = AdmittedMaintenanceActs(self.cap_maintenance_merge, context)
        workflows = (
            AdmittedWorkflowRunner(self.workflows, self.admission, context, repo)
            if self.workflows is not None
            else None
        )

        def dispatch() -> dict:
            helper_judge_oneshot_runs(
                rows,
                observations=scoped,
                config=self.config,
                credentials=self.credentials,
                door=self.door,
                events=self.events,
                macts=macts,
                msource=self.msource,
                psource=self.psource,
                studios=self.studios,
                worker_image=self.worker_image,
                workflows=workflows,
                cap_delivery_config=self.cap_delivery_config,
                cap_git_roles=self.cap_git_roles,
                cap_instantiation=self.cap_instantiation,
                cap_list_git_identities=self.cap_list_git_identities,
                cap_pair_credential_held=self.cap_pair_credential_held,
                cap_run_graph=self.cap_run_graph,
                cap_run_retention=self.cap_run_retention,
                compiler=self.compiler,
                context=context,
            )
            self.observations.oneshot.update(scoped.oneshot)
            return {
                "repo": repo,
                "pending": len(scoped.oneshot),
                "settled": sum(
                    bool(entry.get("acted")) for entry in scoped.oneshot.values()
                ),
            }

        return self.admission.execute(
            context,
            "maintenance.reconcile",
            repo,
            operation_id,
            {"runs": [row.handle for row in rows]},
            dispatch,
        )
