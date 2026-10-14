"""Authorize a run's source identity and preserve its durable command outcome."""

from collections.abc import Callable

from orchestrator.application.ports.outbound.workflow_runner import WorkflowRunner
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.command_context import CommandContext
from orchestrator.domain.model.operation_receipt import OperationReceipt
from orchestrator.domain.model.workflow_metadata import WorkflowMetadata


def execute_run_command(
    *,
    workflows: WorkflowRunner | None,
    admission: OperationAdmission,
    context: CommandContext,
    action: str,
    operation_id: str,
    handle: str,
    expected_revision: str | None,
    payload: dict,
    check: Callable[[WorkflowMetadata], None],
    dispatch: Callable[[WorkflowMetadata], dict],
) -> dict:
    context.authorize(action)
    evidence: dict = {}
    observed: list[WorkflowMetadata] = []

    def validate() -> None:
        if workflows is None:
            raise SourceUnavailable("No workflow executor is configured.")
        metadata = workflows.metadata_of(handle)
        if not metadata.repository or not metadata.uid or not metadata.resource_version:
            raise SourceUnavailable("The workflow has incomplete ownership metadata.")
        context.authorize(action, metadata.repository)
        if expected_revision and expected_revision != metadata.resource_version:
            raise Conflict("The workflow changed; refresh its state before acting.")
        check(metadata)
        evidence.update(
            repository=metadata.repository,
            uid=metadata.uid,
            resource_version=metadata.resource_version,
            handle=handle,
        )
        observed.append(metadata)

    def validate_retained(receipt: OperationReceipt) -> None:
        repository = receipt.evidence.get("repository")
        if not repository:
            raise OperationUnknown(receipt.key)
        context.authorize(action, repository)

    return admission.execute(
        context,
        action,
        "",
        operation_id,
        {"handle": handle, "expected_revision": expected_revision, **payload},
        lambda: dispatch(observed[0]),
        evidence=evidence,
        validate=validate,
        validate_retained=validate_retained,
    )
