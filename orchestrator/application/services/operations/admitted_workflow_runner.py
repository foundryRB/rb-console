"""Delegated submissions with stable durable replay barriers."""

from __future__ import annotations

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.delegated_grants import (
    DelegatedGrants,
)
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.domain.delivery import same_repository
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.compiled_workflow import CompiledWorkflow
from orchestrator.domain.model.execution_graph import ExecutionGraph
from orchestrator.domain.model.run_inventory_entry import RunInventoryEntry
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata


class AdmittedWorkflowRunner:
    def __init__(
        self,
        runner: WorkflowRunner,
        admission: OperationAdmission,
        context: CommandContext,
        repo: str,
    ) -> None:
        self.runner, self.admission, self.context, self.repo = (
            runner,
            admission,
            context,
            repo,
        )

    def submit(
        self, workflow: CompiledWorkflow, *, delegated_grant_id: str | None = None
    ) -> str:
        self.context.authorize("maintenance.drive", self.repo)
        if not workflow.name or not same_repository(workflow.repository, self.repo):
            raise PermissionDenied(
                "A delegated submission requires a stable scoped run identity"
            )

        def dispatch() -> str:
            grant = DelegatedGrants(
                self.admission.receipts, self.context.authorization_revision
            ).issue(self.context, self.repo, workflow.run_id, 3600)
            return self.runner.submit(workflow, delegated_grant_id=grant["grant_id"])

        return self.admission.execute(
            self.context,
            "maintenance.drive",
            self.repo,
            "reconcile:submit:" + workflow.name,
            safe_value(workflow),
            dispatch,
        )

    def metadata_of(self, handle: str) -> WorkflowMetadata:
        metadata = self.runner.metadata_of(handle)
        if not same_repository(metadata.repository, self.repo):
            raise PermissionDenied("The delegated run is outside its repository scope")
        return metadata

    def status(self, handle: str) -> str:
        return self.runner.status(handle)

    def list_runs(self) -> list[RunInventoryEntry]:
        return self.runner.list_runs()

    def graph(self, handle: str) -> ExecutionGraph:
        return self.runner.graph(handle)

    def logs(self, handle: str, tail: int = 400, node_id: str | None = None) -> str:
        return self.runner.logs(handle, tail, node_id)

    def stop(
        self, handle: str, terminate: bool = False, reason: str = "operator", **kwargs
    ) -> str:
        raise PermissionDenied("The scheduler grant permits no run control")

    def resume(self, handle: str, **kwargs) -> str:
        raise PermissionDenied("The scheduler grant permits no run control")

    def delete(self, handle: str) -> str:
        raise PermissionDenied("The scheduler grant permits no executor deletion")
