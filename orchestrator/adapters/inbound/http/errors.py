import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from orchestrator.adapters.inbound.http.models.error_response import ErrorResponse
from orchestrator.application.services.operations.safe_reason import safe_reason
from orchestrator.domain.exceptions.conflict import Conflict
from orchestrator.domain.exceptions.operation_unknown import OperationUnknown
from orchestrator.domain.exceptions.permission_denied import PermissionDenied
from orchestrator.domain.exceptions.source_unavailable import SourceUnavailable

ERROR_RESPONSES = {status: {"model": ErrorResponse} for status in (403, 409, 422, 503)}

_log = logging.getLogger(__name__)


def register_errors(app: FastAPI) -> None:
    def response(status: int, code: str, message: str, **extra) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={"code": code, "message": message, "detail": message, **extra},
        )

    @app.exception_handler(SourceUnavailable)
    def unavailable(request: Request, exc: SourceUnavailable) -> JSONResponse:
        # The source's own reason, safe to show, names which one failed (INT-FC-R190).
        reason = safe_reason(exc, named=False)
        _log.warning("%s %s: source unavailable: %s", request.method, request.url.path, reason)
        result = response(
            503,
            "source_unavailable",
            f"The source is unavailable ({reason}). Its last observation may be stale.",
        )
        result.headers["Retry-After"] = str(max(1, int(exc.retry_after)))
        return result

    @app.exception_handler(PermissionDenied)
    def denied(request: Request, exc: PermissionDenied) -> JSONResponse:
        return response(
            403, "permission_denied", "No current grant permits this operation."
        )

    @app.exception_handler(Conflict)
    def conflict(request: Request, exc: Conflict) -> JSONResponse:
        return response(409, "conflict", str(exc))

    @app.exception_handler(OperationUnknown)
    def unknown(request: Request, exc: OperationUnknown) -> JSONResponse:
        return response(
            409, "operation_unknown", str(exc), operation_key=exc.operation_key
        )

    @app.exception_handler(RequestValidationError)
    def invalid_body(request: Request, exc: RequestValidationError) -> JSONResponse:
        return response(
            422, "invalid_request", "The request does not match the API contract."
        )

    @app.exception_handler(ValueError)
    def invalid(request: Request, exc: ValueError) -> JSONResponse:
        return response(422, "invalid_evidence", str(exc))

    @app.exception_handler(HTTPException)
    def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return response(exc.status_code, "request_refused", str(exc.detail))
