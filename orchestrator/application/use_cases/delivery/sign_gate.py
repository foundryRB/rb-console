"""SignGate over consumed application contracts."""

from __future__ import annotations

import datetime
from functools import partial
from typing import get_type_hints

from orchestrator.application.events import GATE_SIGNED, state_fact
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.delivery.fresh_state import helper_fresh_state
from orchestrator.application.services.delivery.release_parked_run import (
    helper_release_parked_run,
)
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.projections.remember import helper_remember
from orchestrator.domain.delivery import AWAITING_GATE
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState


class SignGate:
    def __init__(
        self,
        *,
        events: EventPublisher | None,
        index: DeliveryIndex | None,
        repos: RepoStore,
        source: DeliverySource | None,
        workflows: WorkflowRunner | None,
        cap_status: StatusPort,
        admission: OperationAdmission,
    ) -> None:
        self.events = events
        self.index = index
        self.repos = repos
        self.source = source
        self.workflows = workflows
        self.cap_status = cap_status
        self.admission = admission

    def _execute(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
        prepared: DeliveryState,
    ) -> DeliveryState:
        """Apply the admitted sign gate command using its prepared inputs."""
        state = prepared
        phase = next(p for p in state.lifecycle.phases if p.name == state.phase)
        self.repos.write_gate(
            repo,
            phase.record,
            datetime.datetime.now(datetime.UTC).date().isoformat(),
            definition=state.lifecycle,
            expected_revision=state.revision,
        )
        gate = state.blocked_gate
        scratch_ref = state.scratch_ref
        state = partial(
            helper_remember,
            index=self.index,
            source=self.source,
            cap_status=self.cap_status,
        )(repo)
        partial(helper_release_parked_run, workflows=self.workflows)(
            context.repository_id(repo), gate, scratch_ref=scratch_ref
        )
        state_fact(
            self.events,
            event_type=GATE_SIGNED,
            subject=repo,
            data={"repo": repo, "gate": gate},
        )
        return state

    def execute(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        context.authorize("delivery.sign", repo)
        result = []
        prepared = []

        def dispatch():
            value = self._execute(
                repo=repo,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
                prepared=prepared[0],
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.sign",
            repo,
            operation_id,
            safe_value({"repo": repo, "expected_revision": expected_revision}),
            dispatch,
            secret_write=False,
            validate=lambda: prepared.append(
                self._validate(
                    repo=repo,
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

    def _validate(
        self,
        repo: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        """Validate fresh sign gate preconditions before recording command intent."""
        state = partial(
            helper_fresh_state, source=self.source, cap_status=self.cap_status
        )(repo)
        if expected_revision and expected_revision.strip('"') != state.revision:
            raise Conflict("The delivery revision changed")
        if state.status != AWAITING_GATE or not state.blocked_gate:
            raise ValueError("this delivery is not awaiting a gate")
        record = next(
            (p.record for p in state.lifecycle.phases if p.name == state.phase), None
        )
        if record is None:
            raise ValueError(f"no record for phase {state.phase}")
        if record not in state.reviewed_records:
            raise ValueError("The gate requires a recorded fresh review")
        return state
