"""Custom exceptions and global exception handlers.

Every error leaves the API in the same shape:
    {"error": {"code": "...", "message": "...", "details": ...}}
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, application-level errors."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class FileTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"


def _error_response(
    status_code: int, code: str, message: str, details: object | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.details)


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _error_response(exc.status_code, "http_error", str(exc.detail))


async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        422,
        "request_validation_error",
        "The request contains invalid data.",
        jsonable_encoder(exc.errors()),
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    # Log the real error server-side; never leak internals to the client.
    logger.exception("Unhandled error: %s", exc)
    return _error_response(500, "internal_server_error", "An unexpected error occurred.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
