from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.config import config_dto, driver_dto
from orchestrator.adapters.inbound.http.models.agent import Agent
from orchestrator.adapters.inbound.http.models.agent_in import AgentIn
from orchestrator.adapters.inbound.http.models.agents_response import AgentsResponse
from orchestrator.adapters.inbound.http.models.apply_delivery_in import ApplyDeliveryIn
from orchestrator.adapters.inbound.http.models.apply_driver_in import ApplyDriverIn
from orchestrator.adapters.inbound.http.models.deleted_response import DeletedResponse
from orchestrator.adapters.inbound.http.models.delivery_config import DeliveryConfig
from orchestrator.adapters.inbound.http.models.driver_info import DriverInfo
from orchestrator.adapters.inbound.http.session import command_arguments, viewer

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/agents", response_model=AgentsResponse, response_model_exclude_unset=True
    )
    def list_agents(*, request: Request) -> dict:
        return {"agents": service.list_agents.execute(viewer=viewer(request))}

    @router.post("/api/agents", response_model=Agent, response_model_exclude_unset=True)
    def set_agent(body: AgentIn, *, request: Request) -> dict:
        try:
            return service.set_agent.execute(
                body.name,
                body.provider,
                body.base_url,
                body.model,
                body.credential,
                body.models,
                level=body.level,
                team=body.team,
                **command_arguments(request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete(
        "/api/agents/{name}",
        response_model=DeletedResponse,
        response_model_exclude_unset=True,
    )
    def delete_agent(name: str, *, request: Request) -> dict:
        try:
            service.delete_agent.execute(name, **command_arguments(request))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"deleted": name}

    @router.post(
        "/api/agents/{name}/apply-driver",
        response_model=DriverInfo,
        response_model_exclude_unset=True,
    )
    def apply_agent_to_driver(
        name: str, body: ApplyDriverIn | None = None, *, request: Request
    ) -> dict:
        try:
            return driver_dto(
                service.apply_agent_to_driver.execute(
                    name, body.model if body else None, **command_arguments(request)
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/agents/{name}/apply-delivery",
        response_model=DeliveryConfig,
        response_model_exclude_unset=True,
    )
    def apply_agent_to_delivery(
        name: str, body: ApplyDeliveryIn, *, request: Request
    ) -> dict:
        try:
            return config_dto(
                service.apply_agent_to_delivery.execute(
                    body.target, name, body.model or None, **command_arguments(request)
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
