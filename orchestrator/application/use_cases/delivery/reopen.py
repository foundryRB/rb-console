"""Reopen over consumed application contracts."""

from __future__ import annotations

from functools import partial
from typing import get_type_hints

from orchestrator.application.events import PHASE_REOPENED, state_fact
from orchestrator.application.ports.inbound.projections.status import StatusPort
from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.event_publisher import EventPublisher
from orchestrator.application.ports.outbound.projections.index import DeliveryIndex
from orchestrator.application.ports.outbound.repo_store import RepoStore
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.application.services.projections.remember import helper_remember
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.delivery_state import DeliveryState


class Reopen:
    def __init__(
        self,
        *,
        events: EventPublisher | None,
        index: DeliveryIndex | None,
        repos: RepoStore,
        source: DeliverySource | None,
        cap_status: StatusPort,
        admission: OperationAdmission,
    ) -> None:
        self.events = events
        self.index = index
        self.repos = repos
        self.source = source
        self.cap_status = cap_status
        self.admission = admission

    def _execute(
        self,
        repo: str,
        phase: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
        prepared: DeliveryState,
    ) -> DeliveryState:
        """Apply the admitted reopen command using its prepared inputs."""
        state = prepared
        record = next(
            (p.record for p in state.lifecycle.phases if p.name == phase), None
        )
        if not record:
            raise ValueError(f"no gated record for phase {phase!r}")
        self.repos.reopen_gate(repo, record, expected_revision=state.revision)
        state = partial(
            helper_remember,
            index=self.index,
            source=self.source,
            cap_status=self.cap_status,
        )(repo)
        state_fact(
            self.events,
            event_type=PHASE_REOPENED,
            subject=repo,
            data={"repo": repo, "phase": phase},
        )
        return state

    def execute(
        self,
        repo: str,
        phase: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        context.authorize("delivery.reopen", repo)
        result = []
        prepared = []

        def dispatch():
            value = self._execute(
                repo=repo,
                phase=phase,
                context=context,
                operation_id=operation_id,
                expected_revision=expected_revision,
                prepared=prepared[0],
            )
            result.append(value)
            return safe_value(value)

        retained = self.admission.execute(
            context,
            "delivery.reopen",
            repo,
            operation_id,
            safe_value(
                {"repo": repo, "phase": phase, "expected_revision": expected_revision}
            ),
            dispatch,
            secret_write=False,
            validate=lambda: prepared.append(
                self._validate(
                    repo=repo,
                    phase=phase,
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
        phase: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> DeliveryState:
        """Validate fresh reopen preconditions before recording command intent."""
        state = self.source.state_of(repo)
        if expected_revision and expected_revision.strip('"') != state.revision:
            raise Conflict("The delivery revision changed")
        record = next(
            (p.record for p in state.lifecycle.phases if p.name == phase), None
        )
        if not record:
            raise ValueError(f"no gated record for phase {phase!r}")
        return state
