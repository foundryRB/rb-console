"""Drive over consumed application contracts."""

from __future__ import annotations

import datetime
from dataclasses import replace
from functools import partial
from typing import get_type_hints

from orchestrator.application.events import PHASE_STARTED, state_fact
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.promotion.instantiation import (
    InstantiationPort,
)
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.inbound.settings.git_roles import GitRolesPort
from orchestrator.application.ports.inbound.settings.pair_credential_held import (
    PairCredentialHeldPort,
)
from orchestrator.application.ports.inbound.studios.tool_urls import ToolUrlsPort
from orchestrator.application.ports.outbound.config_store import ConfigStore
from orchestrator.application.ports.outbound.credential_store import CredentialStore
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.execution.workflow_compiler import (
    WorkflowCompiler,
)
from orchestrator.application.ports.outbound.promotion_source import PromotionSource
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.ports.outbound.repositories.repository_incarnations import (
    RepositoryIncarnations,
)
from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.delivery.demo_source import helper_demo_source
from orchestrator.application.services.delivery.fresh_state import helper_fresh_state
from orchestrator.application.services.identity.slug import helper_slug
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.promotion.home_target import helper_home_target
from orchestrator.application.services.promotion.pair_home import helper_pair_home
from orchestrator.application.services.runs.prepare_config import prepare_config
from orchestrator.application.services.runs.retention_gc import helper_retention_gc
from orchestrator.application.services.runs.supersede_runs import helper_supersede_runs
from orchestrator.application.services.settings.git_identities_map import (
    helper_git_identities_map,
)
from orchestrator.application.services.studios.agent_catalog import helper_agent_catalog
from orchestrator.domain.current_lifecycle import CURRENT_PLAYBOOK_REF
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.delivery.drive_result import DriveResult
from orchestrator.domain.model.delivery_state import DeliveryState
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.model.run_mode import RunMode
from orchestrator.domain.services.runtime_pin import worker_image_for


class Drive:
    def __init__(
        self,
        *,
        config: ConfigStore | None,
        credentials: CredentialStore | None,
        events: EventPublisher | None,
        psource: PromotionSource | None,
        repos: RepoStore,
        source: DeliverySource | None,
        studios: StudioGateway | None,
        worker_image: str,
        workflows: WorkflowRunner | None,
        cap_git_roles: GitRolesPort,
        cap_instantiation: InstantiationPort,
        cap_pair_credential_held: PairCredentialHeldPort,
        cap_run_retention: RunRetentionPort,
        cap_status: StatusPort,
        cap_tool_urls: ToolUrlsPort,
        admission: OperationAdmission,
        compiler: WorkflowCompiler,
        incarnations: RepositoryIncarnations,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self.events = events
        self.psource = psource
        self.repos = repos
        self.source = source
        self.studios = studios
        self.worker_image = worker_image
        self.workflows = workflows
        self.cap_git_roles = cap_git_roles
        self.cap_instantiation = cap_instantiation
        self.cap_pair_credential_held = cap_pair_credential_held
        self.cap_run_retention = cap_run_retention
        self.cap_status = cap_status
        self.cap_tool_urls = cap_tool_urls
        self.admission = admission
        self.compiler = compiler
        self.incarnations = incarnations

    def _execute(
        self,
        repo: str,
        config: RunConfig,
        run_id: str,
        from_phase: str | None = None,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
        prepared: tuple[DeliveryState, RunConfig, CompiledWorkflow, str, str, dict | None]
        | None = None,
    ) -> DriveResult:
        state, effective, workflow, slug, entry, pin = prepared or self._prepare(
            repo,
            config,
            run_id,
            from_phase,
            feedback,
            context=context,
            operation_id=operation_id,
            expected_revision=expected_revision,
        )
        if pin is not None:
            self.repos.write_config(repo, pin, lifecycle=state.lifecycle)
        if config.worker_credential and self.credentials is not None:
            self.credentials.put_delivery(slug, config.worker_credential)
        if entry:
            self.repos.append_journal(repo, entry)
        if self.workflows is not None:
            helper_supersede_runs(context.repository_id(repo), workflows=self.workflows)
        handle = self.workflows.submit(workflow) if self.workflows is not None else None
        state_fact(
            self.events,
            event_type=PHASE_STARTED,
            subject=repo,
            data={
                "repo": repo,
                "phase": from_phase or state.phase,
                "run_id": run_id,
                "handle": handle,
                "mode": getattr(effective.mode, "value", effective.mode),
                "revision": bool(feedback),
            },
        )
        return DriveResult(run_id=run_id, state=state, workflow=workflow, handle=handle)

    def execute(
        self,
        repo: str,
        config: RunConfig,
        run_id: str,
        from_phase: str | None = None,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DriveResult:
        context.authorize("delivery.drive", repo)
        if context.initiator_kind == "machine" and (
            config.worker_credential
            or config.worker_base_url
            or config.worker_model
            or config.worker_provider != RunConfig.worker_provider
        ):
            # The machine caller runs on the agent applied to the line, so the console's
            # stored credential only ever reaches that agent's own endpoint (INT-FC-R173).
            raise PermissionDenied(
                "A machine drive names no worker settings: apply an agent to the line instead."
            )
        # The write right is the console's own fact once the caller is admitted, never the
        # body's assertion (INT-FC-R176): the browser sends none, as the promotion drive's
        # config carries none.
        config = replace(config, repo_rights=True)
        run_id = (
            "d-"
            + self.admission.key(context, "delivery.drive", repo, operation_id)[:12]
        )
        result = []
        prepared = []

        def dispatch():
            value = self._execute(
                repo=repo,
                config=config,
                run_id=run_id,
                from_phase=from_phase,
                feedback=feedback,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
                prepared=prepared[0],
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.drive",
            repo,
            operation_id,
            safe_value(
                {
                    "repo": repo,
                    "config": config,
                    "run_id": run_id,
                    "from_phase": from_phase,
                    "feedback": feedback,
                    "expected_revision": expected_revision,
                }
            ),
            dispatch,
            secret_write=bool(config.worker_credential),
            validate=lambda: prepared.append(
                self._prepare(
                    repo=repo,
                    config=config,
                    run_id=run_id,
                    from_phase=from_phase,
                    feedback=feedback,
                    context=context,
                    operation_id=operation_id,
                    expected_revision=expected_revision,
                )
            ),
        )
        if result:
            return result[0]
        return restore_result(
            retained, get_type_hints(self._execute).get("return", object)
        )

    def _prepare(
        self,
        repo: str,
        config: RunConfig,
        run_id: str,
        from_phase: str | None = None,
        feedback: str | None = None,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> tuple[DeliveryState, RunConfig, CompiledWorkflow, str, str, dict | None]:
        """Capture fresh line evidence and compile the remaining pinned phases.

        A selected from_phase adopts available studio work into the starting phase.
        Feedback records the revision request and reaches the selected worker prompt.
        Compilation completes before admitted credential or executor effects.
        """
        state = partial(
            helper_fresh_state, source=self.source, cap_status=self.cap_status
        )(repo)
        line_config = self.source.read_config(repo, revision=state.revision)
        pin = None
        if not state.lifecycle.source_ref:
            # A line no console pinned (opened by hand, or by an earlier console) adopts the
            # installed definition on its first drive; the dispatch records the pin beside the
            # line's configuration before the run is submitted (INT-FC-R172).
            state = replace(
                state,
                lifecycle=replace(
                    state.lifecycle,
                    source_ref=CURRENT_PLAYBOOK_REF,
                    worker_image=self.worker_image,
                ),
            )
            pin = {k: v for k, v in line_config.items() if k not in {"presence", "lifecycle"}}
        worker_image = worker_image_for(state.lifecycle, self.worker_image)
        phases = tuple(p for p in state.lifecycle.phases if p.completion == "record")
        terminal_phase = next(
            (p for p in state.lifecycle.phases if p.completion == "journal"),
            state.lifecycle.phases[-1],
        )
        if expected_revision and expected_revision.strip('"') != state.revision:
            raise Conflict("The delivery revision changed")
        if not config.repo_target or not config.repo_rights:
            raise ValueError(
                "config incomplete: a repo target and its rights are required"
            )
        if from_phase is not None and from_phase not in {p.name for p in phases} | {
            terminal_phase.name
        }:
            raise ValueError(f"unknown phase {from_phase!r}")
        slug = partial(helper_slug)(repo)
        config, _identity = prepare_config(
            repo,
            config,
            config=self.config,
            credentials=self.credentials,
            incarnations=self.incarnations,
            context=context,
        )
        config = replace(config, mode=RunMode(line_config.get("mode") or "interactive"))
        feedback = (feedback or "").strip()
        entry = ""
        if feedback:
            phase_name = from_phase or state.phase or ""
            gate = (
                next((p.gate for p in phases if p.name == phase_name), "")
                or phase_name
                or "line"
            )
            entry = f"## {gate} gate: re-driven {datetime.datetime.now(datetime.UTC).date().isoformat()}\n\n{feedback}"
        credential_secret = (
            self.credentials.delivery_ref(slug) if self.credentials is not None else ""
        )
        home_target = partial(
            helper_home_target,
            psource=self.psource,
            cap_instantiation=self.cap_instantiation,
        )(repo)
        home = partial(
            helper_pair_home, cap_pair_credential_held=self.cap_pair_credential_held
        )(home_target)
        if home_target is not None and home is None:
            raise ValueError(
                f"this app's home is {home_target.repo} and the platform holds no credential named {home_target.credential or '(unnamed)'}: nothing can clone their code or open a pull request on it. Register it in Settings -> Pair credentials."
            )
        workflow = self.compiler.compile_delivery(
            repo,
            state,
            config,
            run_id=run_id,
            credential_secret=credential_secret,
            from_phase=from_phase,
            feedback=feedback,
            worker_image=worker_image,
            git_identities=partial(
                helper_git_identities_map,
                config=self.config,
                cap_git_roles=self.cap_git_roles,
            )(),
            retention=partial(
                helper_retention_gc, cap_run_retention=self.cap_run_retention
            )(),
            home=home,
            catalog=partial(helper_agent_catalog, studios=self.studios)(),
            tool_urls=self.cap_tool_urls.execute(state.lifecycle),
            demo=partial(helper_demo_source, studios=self.studios)(repo, state),
        )
        return (state, config, workflow, slug, entry if feedback else "", pin)
