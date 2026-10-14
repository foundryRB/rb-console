from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.mappers.fleet import fleet_dto
from orchestrator.adapters.inbound.http.models.chat_turn import ChatTurn
from orchestrator.adapters.inbound.http.models.fleet_chat_in import FleetChatIn
from orchestrator.adapters.inbound.http.models.fleet_response import FleetResponse
from orchestrator.adapters.inbound.http.session import viewer

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.post(
        "/api/fleet/refresh", response_model=ChatTurn, response_model_exclude_unset=True
    )
    def fleet_refresh(include_hidden: bool = False, *, request: Request) -> dict:
        reader = viewer(request)

        def run() -> dict:
            service.refresh.execute(force=True)
            since, why = service.fleet_staleness.execute()
            return {
                **fleet_dto(
                    service.fleet.execute(include_hidden, viewer=reader), since, why
                ),
                **service.snapshot_metadata.execute(),
            }

        return service.start_turn.execute(run)

    @router.get(
        "/api/fleet", response_model=FleetResponse, response_model_exclude_unset=True
    )
    def fleet(include_hidden: bool = False, *, request: Request) -> dict:
        since, why = service.fleet_staleness.execute()
        return {
            **fleet_dto(
                service.fleet.execute(include_hidden, viewer=viewer(request)), since, why
            ),
            **service.snapshot_metadata.execute(),
        }

    @router.post(
        "/api/fleet/chat", response_model=ChatTurn, response_model_exclude_unset=True
    )
    def fleet_chat(body: FleetChatIn, *, request: Request) -> dict:
        return service.fleet_chat_start.execute(
            body.message,
            [message.model_dump() for message in body.history],
            viewer=viewer(request),
        )

    return router
