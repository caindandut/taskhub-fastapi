import logging
import re
import time
import uuid
from collections.abc import Iterable

from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings, get_settings
from app.core.constants import (
    MAX_REQUEST_ID_LENGTH,
    PROCESS_TIME_HEADER,
    REQUEST_ID_HEADER,
)
from app.core.logging import reset_request_id, set_request_id

logger = logging.getLogger("app.access")

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("latin-1")


def resolve_request_id(headers: Iterable[tuple[bytes, bytes]]) -> str:
    """Return a validated incoming X-Request-ID or generate a fresh UUID hex."""
    for name, raw_value in headers:
        if name.lower() == _REQUEST_ID_HEADER_BYTES:
            candidate = raw_value.decode("latin-1", errors="ignore").strip()
            if 1 <= len(
                candidate
            ) <= MAX_REQUEST_ID_LENGTH and _REQUEST_ID_PATTERN.fullmatch(candidate):
                return candidate
            break
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Attach correlation ID, timing header, and structured access logs per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(scope.get("headers", ()))
        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client")
        client_ip = client[0] if client else None

        start_time = time.perf_counter()
        status_code = 500
        failed = False
        token = set_request_id(request_id)

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                elapsed_seconds = time.perf_counter() - start_time
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id
                headers[PROCESS_TIME_HEADER] = f"{elapsed_seconds:.6f}"
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            failed = True
            state["unhandled_logged"] = True
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.exception(
                "%s %s -> 500 (%.2fms)",
                method,
                path,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            raise
        finally:
            if not failed:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.info(
                    "%s %s -> %s (%.2fms)",
                    method,
                    path,
                    status_code,
                    duration_ms,
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip,
                    },
                )
            reset_request_id(token)


class DynamicCORSMiddleware:
    """Delegate HTTP requests to CORSMiddleware configured from active Settings."""

    def __init__(self, app: ASGIApp, settings: Settings | None = None) -> None:
        self.app = app
        self._explicit_settings = settings
        self._cached_settings: Settings | None = None
        self._cors_middleware: CORSMiddleware | None = None

    def _get_middleware(self) -> CORSMiddleware:
        active_settings = self._explicit_settings or get_settings()
        if (
            self._cors_middleware is None
            or active_settings is not self._cached_settings
        ):
            self._cached_settings = active_settings
            self._cors_middleware = CORSMiddleware(
                app=self.app,
                allow_origins=active_settings.cors_origins,
                allow_credentials=active_settings.cors_allow_credentials,
                allow_methods=active_settings.cors_allow_methods,
                allow_headers=active_settings.cors_allow_headers,
                expose_headers=[REQUEST_ID_HEADER, PROCESS_TIME_HEADER],
            )
        return self._cors_middleware

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await self._get_middleware()(scope, receive, send)
