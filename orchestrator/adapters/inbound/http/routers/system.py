from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, Response

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.models.health_response import HealthResponse
from orchestrator.adapters.inbound.http.models.ready_response import ReadyResponse

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/health", response_model=HealthResponse, response_model_exclude_unset=True
    )
    def health() -> dict:
        return {"status": "ok"}

    @router.get(
        "/api/ready", response_model=ReadyResponse, response_model_exclude_unset=True
    )
    def ready(response: Response, request: Request) -> dict:
        if not request.app.state.ready:
            response.status_code = 503
        return {"ready": bool(request.app.state.ready)}

    return router
