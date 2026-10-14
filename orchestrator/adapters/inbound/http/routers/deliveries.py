from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.config import config_dto
from orchestrator.adapters.inbound.http.mappers.delivery import (
    action_dto,
    drive_dto,
    overview_dto,
    state_dto,
)
from orchestrator.adapters.inbound.http.models.action import Action
from orchestrator.adapters.inbound.http.models.chat_in import ChatIn
from orchestrator.adapters.inbound.http.models.chat_turn import ChatTurn
from orchestrator.adapters.inbound.http.models.close_in import CloseIn
from orchestrator.adapters.inbound.http.models.deliveries_response import (
    DeliveriesResponse,
)
from orchestrator.adapters.inbound.http.models.delivery_config import DeliveryConfig
from orchestrator.adapters.inbound.http.models.delivery_config_in import (
    DeliveryConfigIn,
)
from orchestrator.adapters.inbound.http.models.drive_result import DriveResult
from orchestrator.adapters.inbound.http.models.establish_in import EstablishIn
from orchestrator.adapters.inbound.http.models.file_content import FileContent
from orchestrator.adapters.inbound.http.models.model_in import ModelIn
from orchestrator.adapters.inbound.http.models.overview import Overview
from orchestrator.adapters.inbound.http.models.reopen_in import ReopenIn
from orchestrator.adapters.inbound.http.models.state import State
from orchestrator.adapters.inbound.http.models.substance import Substance
from orchestrator.adapters.inbound.http.models.target_in import TargetIn
from orchestrator.adapters.inbound.http.models.timeout_in import TimeoutIn
from orchestrator.adapters.inbound.http.models.tree_response import TreeResponse
from orchestrator.adapters.inbound.http.session import (
    command_arguments,
    require_visible,
    viewer,
)
from orchestrator.domain.model.run_config import RunConfig

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/deliveries",
        response_model=DeliveriesResponse,
        response_model_exclude_unset=True,
    )
    def list_deliveries(*, request: Request) -> dict:
        return {
            "deliveries": [
                state_dto(s)
                for s in service.list_deliveries.execute(viewer=viewer(request))
            ],
            **service.snapshot_metadata.execute(deliveries=True),
        }

    @router.get(
        "/api/deliveries/state", response_model=State, response_model_exclude_unset=True
    )
    def delivery_state(repo: str) -> dict:
        return {
            **state_dto(service.status.execute(repo)),
            **service.snapshot_metadata.execute(repo, deliveries=True),
        }

    @router.get(
        "/api/deliveries/overview",
        response_model=Overview,
        response_model_exclude_unset=True,
    )
    def delivery_overview(repo: str) -> dict:
        runs = service.runs.execute()
        graphs = {
            run.handle: service.run_graph.execute(run.handle)
            for run in runs
            if run.handle
        }
        return {
            **overview_dto(service.delivery_overview.execute(repo), runs, graphs),
            **service.snapshot_metadata.execute(repo, deliveries=True),
        }

    @router.get(
        "/api/deliveries/config",
        response_model=DeliveryConfig,
        response_model_exclude_unset=True,
    )
    def get_delivery_config(repo: str) -> dict:
        return config_dto(service.delivery_config.execute(repo))

    @router.post(
        "/api/deliveries/model",
        response_model=DeliveryConfig,
        response_model_exclude_unset=True,
    )
    def set_delivery_model(body: ModelIn, *, request: Request) -> dict:
        secs = round(body.timeout_hours * 3600) if body.timeout_hours else None
        try:
            return config_dto(
                service.set_delivery_model.execute(
                    body.target,
                    body.provider,
                    body.base_url,
                    body.model,
                    body.credential,
                    secs,
                    **command_arguments(request),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/config",
        response_model=DeliveryConfig,
        response_model_exclude_unset=True,
    )
    def set_delivery_config(body: DeliveryConfigIn, *, request: Request) -> dict:
        try:
            return config_dto(
                service.set_delivery_config.execute(
                    body.target, body.mode, **command_arguments(request)
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/timeout",
        response_model=DeliveryConfig,
        response_model_exclude_unset=True,
    )
    def set_delivery_timeout(body: TimeoutIn, *, request: Request) -> dict:
        try:
            return config_dto(
                service.set_delivery_timeout.execute(
                    body.target,
                    round(body.timeout_hours * 3600),
                    **command_arguments(request),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/reopen",
        response_model=State,
        response_model_exclude_unset=True,
    )
    def reopen(body: ReopenIn, *, request: Request) -> dict:
        try:
            return state_dto(
                service.reopen.execute(
                    body.target, body.phase, **command_arguments(request)
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/close", response_model=State, response_model_exclude_unset=True
    )
    def close_line(body: CloseIn, *, request: Request) -> dict:
        try:
            return state_dto(
                service.close_line.execute(body.target, **command_arguments(request))
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/chat",
        response_model=ChatTurn,
        response_model_exclude_unset=True,
    )
    def chat(body: ChatIn, *, request: Request) -> dict:
        require_visible(request, body.target)
        return service.chat_start.execute(
            body.target,
            body.phase,
            body.message,
            [message.model_dump() for message in body.history],
            body.references,
            viewer=viewer(request),
        )

    @router.get(
        "/api/deliveries/tree",
        response_model=TreeResponse,
        response_model_exclude_unset=True,
    )
    def delivery_tree(repo: str) -> dict:
        return {
            "tree": [
                {
                    "path": row.path,
                    "type": {
                        "file": "blob",
                        "directory": "tree",
                        "submodule": "commit",
                    }[row.kind],
                    "size": row.size,
                }
                for row in service.repo_tree.execute(repo)
            ]
        }

    @router.get(
        "/api/deliveries/file",
        response_model=FileContent,
        response_model_exclude_unset=True,
    )
    def delivery_file(repo: str, path: str) -> dict:
        result = service.repo_file.execute(repo, path)
        return {"path": result.path, "content": result.content, "size": result.size}

    @router.get(
        "/api/deliveries/substance",
        response_model=Substance,
        response_model_exclude_unset=True,
    )
    def delivery_substance(repo: str, phase: str) -> dict:
        return service.phase_substance.execute(repo, phase)

    @router.post(
        "/api/deliveries/plan", response_model=Action, response_model_exclude_unset=True
    )
    def plan(body: TargetIn, *, request: Request) -> dict:
        require_visible(request, body.target)
        return action_dto(
            service.plan_next.execute(
                body.target, RunConfig(**body.config.model_dump())
            )
        )

    @router.post(
        "/api/establish", response_model=State, response_model_exclude_unset=True
    )
    def establish(body: EstablishIn, *, request: Request) -> dict:
        source: bytes | None = None
        if body.source_archive:
            try:
                source = base64.b64decode(body.source_archive, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(
                    status_code=422, detail="source_archive is not valid base64"
                ) from exc
        try:
            return state_dto(
                service.establish.execute(
                    body.target,
                    body.request,
                    source,
                    body.source_name,
                    body.app_name,
                    team=body.team,
                    **command_arguments(request),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/api/start", response_model=Action, response_model_exclude_unset=True)
    def start(body: TargetIn, *, request: Request) -> dict:
        try:
            return action_dto(
                service.start.execute(
                    body.target,
                    RunConfig(**body.config.model_dump()),
                    **command_arguments(request),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/drive",
        response_model=DriveResult,
        response_model_exclude_unset=True,
    )
    def drive(body: TargetIn, *, request: Request) -> dict:
        try:
            return drive_dto(
                service.drive.execute(
                    body.target,
                    RunConfig(**body.config.model_dump()),
                    "r-" + uuid4().hex[:8],
                    from_phase=body.from_phase,
                    feedback=body.feedback,
                    **command_arguments(request),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/deliveries/sign", response_model=State, response_model_exclude_unset=True
    )
    def sign(body: TargetIn, *, request: Request) -> dict:
        try:
            return state_dto(
                service.sign_gate.execute(body.target, **command_arguments(request))
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
