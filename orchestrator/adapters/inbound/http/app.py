"""HTTP contract over application capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from orchestrator.adapters.inbound.http.errors import register_errors
from orchestrator.adapters.inbound.http.routers import (
    agents,
    chat,
    config,
    deliveries,
    fleet,
    maintenance,
    operations,
    promotion,
    runs,
    studios,
    system,
)
from orchestrator.adapters.inbound.http.session import _oidc_enabled, command_context
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def create_app(service: ConsoleCapabilities | None = None) -> FastAPI:
    from orchestrator.adapters.inbound.scheduler.lifespan import build_lifespan

    lifespan = build_lifespan(service) if service is not None else None
    app = FastAPI(
        lifespan=lifespan, title="Foundry Console orchestrator", version="0.1.0"
    )
    app.state.ready = False
    # Whose teams a caller's groups name, and which projects each team holds.
    app.state.team_roster = service.team_roster if service is not None else None
    register_errors(app)

    @app.middleware("http")
    async def admit_operator(request: Request, call_next):
        protected = request.url.path.startswith("/api/") and request.url.path not in {
            "/api/health",
            "/api/ready",
        }
        # A request through the execution door is admitted by the door's own rule whether
        # or not the install fronts operators with OIDC (INT-FC-R173).
        door = "X-Console-Door" in request.headers
        if (protected and _oidc_enabled()) or door:
            try:
                context = command_context(request)
            except SourceUnavailable:
                message = "The source is unavailable. Its last observation may be stale."
                return JSONResponse(
                    status_code=503,
                    headers={"Retry-After": "30"},
                    content={
                        "code": "source_unavailable",
                        "message": message,
                        "detail": message,
                    },
                )
            except PermissionDenied:
                message = (
                    "An admitted execution caller is required."
                    if door
                    else "An admitted operator identity is required."
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "permission_denied",
                        "message": message,
                        "detail": message,
                    },
                )
            # A read naming a repository names one the caller sees: a team member reads
            # its teams' projects alone (the door checks its own scope as it admits).
            repo = request.query_params.get("repo", "")
            if not door and request.method == "GET" and repo and not context.sees(repo):
                message = "No current grant permits this operation."
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "permission_denied",
                        "message": message,
                        "detail": message,
                    },
                )
        return await call_next(request)

    for feature in (
        agents,
        chat,
        config,
        deliveries,
        fleet,
        maintenance,
        operations,
        promotion,
        runs,
        studios,
        system,
    ):
        app.include_router(feature.build_router(service))
    return app
