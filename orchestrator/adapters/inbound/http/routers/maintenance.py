from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.maintenance import (
    maintenance_drive_response,
)
from orchestrator.adapters.inbound.http.models.close_response import CloseResponse
from orchestrator.adapters.inbound.http.models.comment_response import CommentResponse
from orchestrator.adapters.inbound.http.models.maint_drive_response import (
    MaintDriveResponse,
)
from orchestrator.adapters.inbound.http.models.maint_inbox_response import (
    MaintInboxResponse,
)
from orchestrator.adapters.inbound.http.models.maint_state import MaintState
from orchestrator.adapters.inbound.http.models.maint_substance import MaintSubstance
from orchestrator.adapters.inbound.http.models.maintenance_close_in import (
    MaintenanceCloseIn,
)
from orchestrator.adapters.inbound.http.models.maintenance_comment_in import (
    MaintenanceCommentIn,
)
from orchestrator.adapters.inbound.http.models.maintenance_drive_in import (
    MaintenanceDriveIn,
)
from orchestrator.adapters.inbound.http.models.maintenance_merge_in import (
    MaintenanceMergeIn,
)
from orchestrator.adapters.inbound.http.models.maintenance_switch_in import (
    MaintenanceSwitchIn,
)
from orchestrator.adapters.inbound.http.models.merge_response import MergeResponse
from orchestrator.adapters.inbound.http.models.switch_response import SwitchResponse
from orchestrator.adapters.inbound.http.session import command_arguments, viewer
from orchestrator.domain.model.run_config import RunConfig
from orchestrator.domain.services.maintenance.ticket_presentation import (
    ticket_presentation,
)

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/maintenance/state",
        response_model=MaintState,
        response_model_exclude_unset=True,
    )
    def maintenance_state(repo: str, include_hidden: bool = False) -> dict:
        return {
            **ticket_presentation(
                service.maintenance_state.execute(repo, include_hidden),
                service.runs.execute(),
            ),
            **service.snapshot_metadata.execute(repo),
        }

    @router.get(
        "/api/maintenance/substance",
        response_model=MaintSubstance,
        response_model_exclude_unset=True,
    )
    def maintenance_substance(repo: str, kind: str, id: int | None = None) -> dict:
        return service.maintenance_substance.execute(repo, kind, id)

    @router.get(
        "/api/maintenance/inbox",
        response_model=MaintInboxResponse,
        response_model_exclude_unset=True,
    )
    def maintenance_inbox(include_hidden: bool = False, *, request: Request) -> dict:
        return {
            **service.maintenance_inbox.execute(include_hidden, viewer=viewer(request)),
            **service.snapshot_metadata.execute(),
        }

    @router.post(
        "/api/maintenance/drive",
        response_model=MaintDriveResponse,
        response_model_exclude_unset=True,
    )
    def maintenance_drive(body: MaintenanceDriveIn, *, request: Request) -> dict:
        try:
            return maintenance_drive_response(
                service.maintenance_drive.execute(
                    body.repo,
                    body.act,
                    body.target,
                    body.mode,
                    RunConfig(**body.config.model_dump()),
                    **command_arguments(request),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/maintenance/merge",
        response_model=MergeResponse,
        response_model_exclude_unset=True,
    )
    def maintenance_merge(body: MaintenanceMergeIn, *, request: Request) -> dict:
        try:
            result = service.maintenance_merge.execute(
                body.repo, body.pr, **command_arguments(request)
            )
            return {"sha": result.commit_id, "merged": result.merged, "message": result.message}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/maintenance/comment",
        response_model=CommentResponse,
        response_model_exclude_unset=True,
    )
    def maintenance_comment(body: MaintenanceCommentIn, *, request: Request) -> dict:
        try:
            result = service.maintenance_comment.execute(
                body.repo, body.number, body.body, **command_arguments(request)
            )
            return {"id": result.comment_id, "html_url": result.url}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/maintenance/close",
        response_model=CloseResponse,
        response_model_exclude_unset=True,
    )
    def maintenance_close(body: MaintenanceCloseIn, *, request: Request) -> dict:
        try:
            result = service.maintenance_close_ticket.execute(
                body.repo, body.number, **command_arguments(request)
            )
            return {"number": result.number, "state": "closed"}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/maintenance/switch-to-delivery",
        response_model=SwitchResponse,
        response_model_exclude_unset=True,
    )
    def maintenance_switch_to_delivery(
        body: MaintenanceSwitchIn, *, request: Request
    ) -> dict:
        try:
            return service.maintenance_switch_to_delivery.execute(
                body.repo, body.number, **command_arguments(request)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
