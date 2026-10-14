"""Resume a scoped workflow whose delivery gates are authoritatively satisfied."""

from orchestrator.application.ports.outbound.delivery_source import DeliverySource
from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.runs.execute_run_command import (
    execute_run_command,
)
from orchestrator.domain.delivery import AWAITING_GATE
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata


class ResumeRun:
    def __init__(
        self,
        *,
        source: DeliverySource | None,
        workflows: WorkflowRunner | None,
        admission: OperationAdmission,
    ) -> None:
        self.source = source
        self.workflows = workflows
        self.admission = admission

    def execute(
        self,
        handle: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        def check(metadata: WorkflowMetadata) -> None:
            if metadata.kind == "delivery":
                if self.source is None:
                    raise SourceUnavailable(
                        "The delivery source is required to verify gates."
                    )
                state = self.source.state_of(metadata.repository)
                if (
                    not state.exists
                    or not metadata.scratch_ref
                    or state.scratch_ref != metadata.scratch_ref
                ):
                    raise Conflict(
                        "The run does not belong to the current delivery line."
                    )
                if state.status == AWAITING_GATE and state.blocked_gate:
                    raise Conflict(
                        f"The {state.blocked_gate} gate is unsigned; sign it before resuming."
                    )
            elif metadata.kind not in {"maintenance", "promotion"}:
                raise Conflict("The workflow kind cannot be verified.")

        return execute_run_command(
            workflows=self.workflows,
            admission=self.admission,
            context=context,
            action="runs.resume",
            operation_id=operation_id,
            handle=handle,
            expected_revision=expected_revision,
            payload={},
            check=check,
            dispatch=lambda metadata: {
                "handle": handle,
                "resumed": self.workflows.resume(
                    handle, expected_version=metadata.resource_version
                ),
            },
        )
