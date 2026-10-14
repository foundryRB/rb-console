from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.models.declare_target_in import DeclareTargetIn
from orchestrator.adapters.inbound.http.models.promotion_drive_in import (
    PromotionDriveIn,
)
from orchestrator.adapters.inbound.http.models.promotion_drive_response import (
    PromotionDriveResponse,
)
from orchestrator.adapters.inbound.http.models.promotion_options import PromotionOptions
from orchestrator.adapters.inbound.http.models.promotion_state import PromotionState
from orchestrator.adapters.inbound.http.models.target_declared_response import (
    TargetDeclaredResponse,
)
from orchestrator.adapters.inbound.http.session import command_arguments

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/promotion/state",
        response_model=PromotionState,
        response_model_exclude_unset=True,
    )
    def promotion_state(repo: str) -> dict:
        return {
            **service.promotion_state.execute(repo),
            **service.snapshot_metadata.execute(repo),
        }

    @router.get(
        "/api/promotion/options",
        response_model=PromotionOptions,
        response_model_exclude_unset=True,
    )
    def promotion_options(repo: str) -> dict:
        return {
            **service.promotion_options.execute(repo),
            **service.snapshot_metadata.execute(repo),
        }

    @router.post(
        "/api/promotion/target",
        response_model=TargetDeclaredResponse,
        response_model_exclude_unset=True,
    )
    def declare_promotion_target(body: DeclareTargetIn, *, request: Request) -> dict:
        try:
            return service.declare_promotion_target.execute(
                body.repo,
                body.model_dump(exclude={"repo"}),
                author=body.author,
                **command_arguments(request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/promotion/drive",
        response_model=PromotionDriveResponse,
        response_model_exclude_unset=True,
    )
    def promotion_drive(body: PromotionDriveIn, *, request: Request) -> dict:
        try:
            result = service.promotion_drive.execute(
                body.repo, body.target, body.release, **command_arguments(request)
            )
            return {"run_id": result.run_id, "handle": result.handle, "target": result.target, "release": result.release, "kind": result.kind.value}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
