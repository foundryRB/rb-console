"""MaintenanceDrive over consumed application contracts."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import cast

from orchestrator.application.events import ACT_LAUNCHED, state_fact
from orchestrator.application.maintenance_modes import parse_mode
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
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
from orchestrator.application.ports.outbound.repositories.repository_incarnations import (
    RepositoryIncarnations,
)
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.maintenance.resolve_feedback import (
    helper_resolve_feedback,
)
from orchestrator.application.services.maintenance.track_oneshot import (
    helper_track_oneshot,
)
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.delegated_grants import (
    DelegatedGrants,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.promotion.pair_home import helper_pair_home
from orchestrator.application.services.runs.prepare_config import (
    prepare_agents,
    prepare_config,
)
from orchestrator.application.services.runs.retention_gc import helper_retention_gc
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.maintenance_command_evidence import (
    MaintenanceCommandEvidence,
)
from orchestrator.domain.model.maintenance_drive_result import MaintenanceDriveResult
from orchestrator.domain.model.maintenance_mode import MaintenanceMode
from orchestrator.domain.model.prepared_maintenance_command import (
    PreparedMaintenanceCommand,
)
from orchestrator.domain.model.run_config import RunConfig


class MaintenanceDrive:
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
        cap_git_roles: GitRolesPort,
        cap_instantiation: InstantiationPort,
        cap_list_git_identities: ListGitIdentitiesPort,
        cap_pair_credential_held: PairCredentialHeldPort,
        cap_run_retention: RunRetentionPort,
        admission: OperationAdmission,
        compiler: WorkflowCompiler,
        incarnations: RepositoryIncarnations,
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
        self.cap_git_roles = cap_git_roles
        self.cap_instantiation = cap_instantiation
        self.cap_list_git_identities = cap_list_git_identities
        self.cap_pair_credential_held = cap_pair_credential_held
        self.cap_run_retention = cap_run_retention
        self.admission = admission
        self.compiler = compiler
        self.incarnations = incarnations

    def _prepare(
        self,
        repo: str,
        act: str,
        target: int | None,
        mode: str | None,
        config: RunConfig,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> PreparedMaintenanceCommand:
        """Compile one maintenance act into a worker run and submit it (INT-FC-R64/R67).
        The mode comes from the request, validated, gated by default; a one-shot resolve
        is tracked for the engine's judge (INT-FC-R65). The credential rides a per-run
        Secret by ref, exactly like a delivery drive.

        Re-driving a resolve over a PR that a review already FAILed threads that review's
        findings as the work order, so the worker revises the open PR (REF-Maintenance
        section 5) rather than opening a duplicate - derived here when the caller sends none,
        the operator-pressed twin of the one-shot engine's re-drive."""
        if self.msource is None or self.psource is None or self.workflows is None:
            raise SourceUnavailable("maintenance execution sources are unavailable")
        from orchestrator.application.promotion import parse_contract
        from orchestrator.domain.model.target_kind import TargetKind
        from orchestrator.domain.services.maintenance_launch import ACT_AGENTS

        if act not in ACT_AGENTS:
            raise ValueError("unsupported maintenance act")
        mode_v = parse_mode(mode)
        revision = self.psource.repository_revision(repo)
        declared, problem = parse_contract(
            self.psource.contract_text(repo, revision=revision)
        )
        if problem:
            raise ValueError("promotion contract is malformed: " + problem)
        installs = self.psource.deploy_installs(repo)
        home = (
            next(
                (item for item in declared if item.kind is TargetKind.REPOSITORY), None
            )
            if not installs
            else None
        )
        pair_home = helper_pair_home(
            home, cap_pair_credential_held=self.cap_pair_credential_held
        )
        if home is not None and pair_home is None:
            raise ValueError(
                f"the repository home credential {home.credential or '(unnamed)'} is not configured"
            )
        contract_revision = revision
        if home is not None:
            if self.door is None:
                raise SourceUnavailable("repository home source is unavailable")
            revision = self.door.repository_revision(
                home.repo, home.branch, home.credential
            )
        if act in {"resolve", "review"}:
            if not target or target < 1:
                raise ValueError("a positive issue or pull request number is required")
            if act == "resolve":
                issue = self.msource.issue(repo, target)
                if issue.state != "open" or issue.is_pull_request:
                    raise ValueError("the selected issue is not open")
            else:
                pr = (
                    self.door.pull_request(home.repo, target, home.credential)
                    if home is not None
                    else self.msource.pr(repo, target)
                )
                if pr is None or pr.state != "open":
                    raise ValueError("the selected pull request is not open")
                revision = pr.head_sha
                if not revision:
                    raise SourceUnavailable("pull request head is unavailable")
                if home is None:
                    self.msource.pr_reviews(repo, target)
                    self.msource.check_runs(repo, revision)
        if expected_revision is not None and revision != expected_revision:
            raise Conflict("maintenance source revision changed")
        cfg, identity = prepare_config(
            repo,
            config,
            config=self.config,
            credentials=self.credentials,
            incarnations=self.incarnations,
            context=context,
        )
        run_id = (
            "m-"
            + self.admission.key(context, "maintenance.drive", repo, operation_id)[:12]
        )
        secret = (
            self.credentials.run_ref(run_id)
            if cfg.worker_credential
            else self.credentials.delivery_ref(helper_slug(repo))
        )
        agents = {ACT_AGENTS[act]}
        if mode_v is MaintenanceMode.ONE_SHOT:
            agents.add("reviewer")
        identities, catalog = prepare_agents(
            agents,
            studios=self.studios,
            config=self.config,
            roles=self.cap_git_roles.execute(),
        )
        feedback = (feedback or "").strip()
        if act == "resolve" and (not feedback):
            feedback = partial(
                helper_resolve_feedback,
                door=self.door,
                msource=self.msource,
                psource=self.psource,
                cap_git_roles=self.cap_git_roles,
                cap_instantiation=self.cap_instantiation,
                cap_list_git_identities=self.cap_list_git_identities,
                home=home,
            )(repo, target)
        workflow = self.compiler.compile_maintenance(
            repo,
            act,
            target,
            mode_v,
            cfg,
            run_id=run_id,
            source_revision=revision,
            credential_secret=secret,
            feedback=feedback,
            worker_image=self.worker_image,
            deadline_seconds=cfg.worker_timeout_seconds,
            git_identities=identities,
            retention=partial(
                helper_retention_gc, cap_run_retention=self.cap_run_retention
            )(),
            home=pair_home,
            catalog=catalog,
        )
        context.authorize("maintenance.drive", repo)
        return PreparedMaintenanceCommand(
            workflow=workflow,
            config=cfg,
            run_id=run_id,
            repository=repo,
            act=act,
            target=target,
            mode=mode_v,
            context=context,
            evidence=MaintenanceCommandEvidence(
                source_revision=revision,
                contract_revision=contract_revision,
                repository_id=identity.stable_id,
                run_id=run_id,
            ),
        )

    def _dispatch(self, prepared: PreparedMaintenanceCommand) -> MaintenanceDriveResult:
        cfg = prepared.config
        if cfg.worker_credential:
            self.credentials.put(prepared.run_id, cfg.worker_credential)
        delegated_grant_id = None
        if prepared.mode is MaintenanceMode.ONE_SHOT:
            context = prepared.context
            grant = DelegatedGrants(
                self.admission.receipts, context.authorization_revision
            ).issue(
                context,
                prepared.repository,
                prepared.run_id,
                cfg.worker_timeout_seconds,
            )
            delegated_grant_id = grant["grant_id"]
        handle = (
            self.workflows.submit(
                prepared.workflow, delegated_grant_id=delegated_grant_id
            )
            if delegated_grant_id
            else self.workflows.submit(prepared.workflow)
        )
        if not handle:
            raise SourceUnavailable("workflow launch outcome is unavailable")
        if prepared.act == "resolve" and prepared.mode is MaintenanceMode.ONE_SHOT:
            helper_track_oneshot(
                handle,
                prepared.repository,
                prepared.target,
                observations=self.observations,
            )
        state_fact(
            self.events,
            event_type=ACT_LAUNCHED,
            subject=prepared.repository,
            data={
                "repo": prepared.repository,
                "act": prepared.act,
                "run_id": prepared.run_id,
                "handle": handle,
            },
        )
        return MaintenanceDriveResult(
            run_id=prepared.run_id, handle=handle, act=prepared.act, mode=prepared.mode
        )

    def execute(
        self,
        repo: str,
        act: str,
        target: int | None,
        mode: str | None,
        config: RunConfig,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> MaintenanceDriveResult:
        context.authorize("maintenance.drive", repo)
        # The write right is the console's own fact once the caller is admitted, never the
        # body's assertion (INT-FC-R176).
        config = replace(config, repo_rights=True)
        result: list[MaintenanceDriveResult] = []
        prepared: list[PreparedMaintenanceCommand] = []
        evidence = {}

        def validate():
            prepared.append(
                self._prepare(
                    repo=repo,
                    act=act,
                    target=target,
                    mode=mode,
                    config=config,
                    feedback=feedback,
                    context=context,
                    operation_id=operation_id,
                    expected_revision=expected_revision,
                )
            )
            evidence.update(safe_value(prepared[0].evidence))

        def dispatch():
            context.authorize("maintenance.drive", repo)
            value = self._dispatch(prepared[0])
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "maintenance.drive",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "act": act,
                    "target": target,
                    "mode": mode,
                    "config": config,
                    "feedback": feedback,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=False,
            validate=validate,
            evidence=evidence,
        )
        if result:
            return result[0]
        return cast(
            MaintenanceDriveResult, restore_result(retained, MaintenanceDriveResult)
        )
