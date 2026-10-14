from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.execution import graph_dto, run_dto
from orchestrator.adapters.inbound.http.models.resume_response import ResumeResponse
from orchestrator.adapters.inbound.http.models.run_control_in import RunControlIn
from orchestrator.adapters.inbound.http.models.run_graph import RunGraph
from orchestrator.adapters.inbound.http.models.run_logs_response import RunLogsResponse
from orchestrator.adapters.inbound.http.models.run_status_response import (
    RunStatusResponse,
)
from orchestrator.adapters.inbound.http.models.runs_response import RunsResponse
from orchestrator.adapters.inbound.http.models.stop_response import StopResponse
from orchestrator.adapters.inbound.http.session import (
    command_arguments,
    require_visible,
    viewer,
)

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/runs", response_model=RunsResponse, response_model_exclude_unset=True
    )
    def runs(*, request: Request) -> dict:
        return {
            "runs": [run_dto(run) for run in service.runs.execute(viewer=viewer(request))],
            **service.snapshot_metadata.execute(),
        }

    @router.get(
        "/api/runs/graph", response_model=RunGraph, response_model_exclude_unset=True
    )
    def run_graph(handle: str, *, request: Request) -> dict:
        require_visible(request, service.run_repository.execute(handle))
        return {
            **graph_dto(service.run_graph.execute(handle)),
            **service.snapshot_metadata.execute(),
        }

    @router.get(
        "/api/runs/logs",
        response_model=RunLogsResponse,
        response_model_exclude_unset=True,
    )
    def run_logs(handle: str, tail: int = 400, node: str = "", *, request: Request) -> dict:
        require_visible(request, service.run_repository.execute(handle))
        return {
            "handle": handle,
            "logs": service.run_logs.execute(handle, tail, node or None),
        }

    @router.post(
        "/api/runs/stop", response_model=StopResponse, response_model_exclude_unset=True
    )
    def stop_run(body: RunControlIn, *, request: Request) -> dict:
        try:
            return service.stop_run.execute(
                body.handle, body.terminate, **command_arguments(request)
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/runs/resume",
        response_model=ResumeResponse,
        response_model_exclude_unset=True,
    )
    def resume_run(body: RunControlIn, *, request: Request) -> dict:
        try:
            return service.resume_run.execute(body.handle, **command_arguments(request))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        "/api/runs/status",
        response_model=RunStatusResponse,
        response_model_exclude_unset=True,
    )
    def run_status(handle: str, *, request: Request) -> dict:
        require_visible(request, service.run_repository.execute(handle))
        return {"handle": handle, "phase": service.run_status.execute(handle)}

    return router
