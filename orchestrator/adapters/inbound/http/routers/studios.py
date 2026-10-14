from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.studios import studios_dto
from orchestrator.adapters.inbound.http.models.app_action_response import (
    AppActionResponse,
)
from orchestrator.adapters.inbound.http.models.studios_response import StudiosResponse
from orchestrator.adapters.inbound.http.session import command_arguments

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/studios",
        response_model=StudiosResponse,
        response_model_exclude_unset=True,
    )
    def studios() -> dict:
        return {
            **studios_dto(service.studios.execute()),
            **service.snapshot_metadata.execute(),
        }

    @router.post(
        "/api/studios/apps/{name}/pause",
        response_model=AppActionResponse,
        response_model_exclude_unset=True,
    )
    def pause_app(name: str, *, request: Request) -> dict:
        try:
            result = service.pause_app.execute(name, **command_arguments(request))
            return {"name": result.name, "paused": result.paused, "status": result.status}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/studios/apps/{name}/resume",
        response_model=AppActionResponse,
        response_model_exclude_unset=True,
    )
    def resume_app(name: str, *, request: Request) -> dict:
        try:
            result = service.resume_app.execute(name, **command_arguments(request))
            return {"name": result.name, "paused": result.paused, "status": result.status}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
