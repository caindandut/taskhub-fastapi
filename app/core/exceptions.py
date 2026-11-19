import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.constants import (
    DATABASE_CONFLICT,
    INTERNAL_SERVER_ERROR,
    REQUEST_ID_HEADER,
)
from app.core.logging import get_request_id

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.headers = headers


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message=message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict") -> None:
        super().__init__(message=message, status_code=status.HTTP_409_CONFLICT)


class AuthenticationException(AppException):
    def __init__(self, message: str = "Could not validate credentials") -> None:
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message=message, status_code=status.HTTP_403_FORBIDDEN)


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request") -> None:
        super().__init__(message=message, status_code=status.HTTP_400_BAD_REQUEST)


def _sanitize_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for err in errors:
        entry: dict[str, Any] = {
            "loc": list(err.get("loc", ())),
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "value_error")),
        }
        ctx = err.get("ctx")
        if isinstance(ctx, dict) and ctx:
            entry["ctx"] = {
                str(key): str(val) if isinstance(val, Exception) else val
                for key, val in ctx.items()
            }
        sanitized.append(jsonable_encoder(entry))
    return sanitized


async def app_exception_handler(request: Request, error: AppException) -> JSONResponse:
    logger.warning(
        "Application error on %s %s (%s): %s",
        request.method,
        request.url.path,
        error.status_code,
        error.message,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": error.status_code,
        },
    )
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.message},
        headers=error.headers,
    )


async def integrity_error_handler(
    request: Request, error: IntegrityError
) -> JSONResponse:
    logger.warning(
        "Database integrity conflict on %s %s",
        request.method,
        request.url.path,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status.HTTP_409_CONFLICT,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": DATABASE_CONFLICT},
    )


async def validation_exception_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    details = _sanitize_validation_errors(error.errors())
    logger.warning(
        "Request validation failed on %s %s (%d error(s))",
        request.method,
        request.url.path,
        len(details),
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
        },
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": details},
    )


async def unhandled_exception_handler(
    request: Request, error: Exception
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or get_request_id()
    if not getattr(request.state, "unhandled_logged", False):
        logger.exception(
            "Unhandled error on %s %s",
            request.method,
            request.url.path,
            exc_info=error,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": INTERNAL_SERVER_ERROR},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
