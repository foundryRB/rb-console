"""Control a freshly observed application's repository under the caller's grant."""

from __future__ import annotations

from orchestrator.application.ports.outbound.studio_gateway import StudioGateway
from orchestrator.application.services.operations.command_payload import safe_value
from orchestrator.application.services.operations.operation_admission import (
    OperationAdmission,
)
from orchestrator.application.services.operations.restore_result import restore_result
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable
from orchestrator.domain.model.app_lifecycle_result import AppLifecycleResult
from orchestrator.domain.model.command_context import CommandContext


class ResumeApp:
    def __init__(
        self, *, studios: StudioGateway | None, admission: OperationAdmission
    ) -> None:
        self.studios, self.admission = studios, admission

    def execute(
        self,
        name: str,
        *,
        context: CommandContext,
        operation_id: str,
        expected_revision: str | None = None,
    ) -> AppLifecycleResult:
        context.authorize("studios.resume")
        if self.studios is None:
            raise SourceUnavailable("The platform studio is unavailable")
        app = next(
            (row for row in self.studios.platform_apps() if row.name == name),
            None,
        )
        if app is None:
            raise SourceUnavailable("The application repository could not be observed")
        repository = app.repository
        if len(repository.split("/")) != 2:
            raise SourceUnavailable("The application repository owner is unavailable")
        context.authorize("studios.resume", repository)
        revision = app.revision
        if expected_revision and expected_revision.strip('"') != revision:
            raise Conflict("The application revision changed")

        def dispatch() -> dict:
            return safe_value(self.studios.resume_app(name))

        retained = self.admission.execute(
            context,
            "studios.resume",
            repository,
            operation_id,
            {"name": name, "revision": revision},
            dispatch,
        )

        return restore_result(retained, AppLifecycleResult)
