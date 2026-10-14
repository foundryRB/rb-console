"""CloseLine over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.events import LINE_CLOSED, state_fact
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.inbound.runs.run_retention import RunRetentionPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.ports.outbound.run_log_store import RunLogStore
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.delivery.fresh_state import helper_fresh_state
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.projections.remember import helper_remember
from orchestrator.application.services.runs.end_runs import helper_end_runs
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState


class CloseLine:
    def __init__(
        self,
        *,
        events: EventPublisher | None,
        index: DeliveryIndex | None,
        repos: RepoStore,
        run_log_store: RunLogStore | None,
        source: DeliverySource | None,
        workflows: WorkflowRunner | None,
        cap_run_retention: RunRetentionPort,
        cap_status: StatusPort,
        admission: OperationAdmission,
    ) -> None:
        self.events = events
        self.index = index
        self.repos = repos
        self.run_log_store = run_log_store
        self.source = source
        self.workflows = workflows
        self.cap_run_retention = cap_run_retention
        self.cap_status = cap_status
        self.admission = admission

    def _execute(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        """Apply the admitted close line command using its prepared inputs."""
        state = partial(
            helper_fresh_state, source=self.source, cap_status=self.cap_status
        )(repo)
        if expected_revision and expected_revision.strip('"') != state.revision:
            raise Conflict("The delivery revision changed")
        if not state.exists:
            raise ValueError("this repo has no delivery scratch to close")
        if self.workflows is not None:
            partial(
                helper_end_runs,
                run_log_store=self.run_log_store,
                workflows=self.workflows,
                cap_run_retention=self.cap_run_retention,
            )(context.repository_id(repo))
        self.repos.close_line(repo, expected_revision=state.revision)
        closed = partial(
            helper_remember,
            index=self.index,
            source=self.source,
            cap_status=self.cap_status,
        )(repo)
        state_fact(
            self.events,
            event_type=LINE_CLOSED,
            subject=repo,
            data={
                "repo": repo,
                "scratch_ref": state.scratch_ref,
                "learned_on": state.learned_on,
            },
        )
        return closed

    def execute(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        context.authorize("delivery.close", repo)
        result = []

        def dispatch():
            value = self._execute(
                repo=repo,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.close",
            repo,
            operation_id,
            safe_value({"repo": repo, "expected_revision": expected_revision}),
            dispatch,
            secret_write=False,
            validate=lambda: self._validate(
                repo=repo,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
            ),
        )
        if result:
            return result[0]
        return restore_result(
            retained, get_type_hints(self._execute).get("return", object)
        )

    def _validate(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        """Validate fresh close line preconditions before recording command intent."""
        state = partial(
            helper_fresh_state, source=self.source, cap_status=self.cap_status
        )(repo)
        if expected_revision and expected_revision.strip('"') != state.revision:
            raise Conflict("The delivery revision changed")
        if not state.exists:
            raise ValueError("this repo has no delivery scratch to close")
