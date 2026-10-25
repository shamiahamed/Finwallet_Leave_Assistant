# Centralised exception handlers producing one consistent JSON error response
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions.errors import AppError
from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    response = JSONResponse(status_code=status, content=body.model_dump(mode="json"))
    # Tell clients how long to wait before retrying a rate-limited request.
    if status == 429:
        response.headers["Retry-After"] = "5"
    return response


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.info("Handled %s: %s", exc.code, exc.message)
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Report field + reason only; never echo submitted input back.
        issues = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "query"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _error(422, "invalid_request", "The request parameters are invalid.", {"errors": issues})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code == 429:
            code = "rate_limit"
        else:
            code = "http_error"
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Return a safe error message without exposing internal exception details.
        logger.exception("Unhandled error")  # stack trace goes to the log only
        return _error(500, "internal_error", "An unexpected error occurred. Please try again.")
