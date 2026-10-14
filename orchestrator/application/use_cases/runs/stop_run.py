"""Stop an authorized workflow at its freshly observed resource version."""

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.runs.execute_run_command import (
    execute_run_command,
)
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.services.run_policy import STOP_OPERATOR


class StopRun:
    def __init__(
        self, *, workflows: WorkflowRunner | None, admission: OperationAdmission
    ) -> None:
        self.workflows = workflows
        self.admission = admission

    def execute(
        self,
        handle: str,
        terminate: bool = False,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> dict:
        return execute_run_command(
            workflows=self.workflows,
            admission=self.admission,
            context=context,
            action="runs.stop",
            operation_id=operation_id,
            handle=handle,
            expected_revision=expected_revision,
            payload={"terminate": terminate},
            check=lambda metadata: None,
            dispatch=lambda metadata: {
                "handle": handle,
                "shutdown": self.workflows.stop(
                    handle,
                    terminate,
                    reason=STOP_OPERATOR,
                    expected_version=metadata.resource_version,
                ),
            },
        )
