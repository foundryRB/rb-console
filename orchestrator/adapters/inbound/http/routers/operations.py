from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from orchestrator.adapters.inbound.http.errors import ERROR_RESPONSES
from orchestrator.adapters.inbound.http.models.operation_receipt_response import (
    OperationReceiptResponse,
)
from orchestrator.adapters.inbound.http.session import command_context

if TYPE_CHECKING:
    from orchestrator.application.ports.inbound.console import ConsoleCapabilities


def build_router(service: ConsoleCapabilities) -> APIRouter:
    router = APIRouter(responses=ERROR_RESPONSES)

    @router.get(
        "/api/operations/{operation_key}",
        response_model=OperationReceiptResponse,
        response_model_exclude_unset=True,
    )
    def inspect_operation(operation_key: str, request: Request) -> dict:
        return service.inspect_operation.execute(
            operation_key, context=command_context(request)
        )

    return router
