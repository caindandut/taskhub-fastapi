import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime

from app.core.constants import DEFAULT_LOG_FORMAT, DEFAULT_LOG_LEVEL

_STRUCTURED_RECORD_FIELDS = (
    "method",
    "path",
    "status_code",
    "duration_ms",
    "client_ip",
)

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return request_id_ctx.get()


def set_request_id(request_id: str | None) -> Token[str | None]:
    return request_id_ctx.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    request_id_ctx.reset(token)


class RequestIdFilter(logging.Filter):
    """Attach the active request correlation ID to every emitted log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as single-line structured JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id is not None:
            payload["request_id"] = request_id

        for field in _STRUCTURED_RECORD_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Format log records in a concise human-readable line."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        request_id = getattr(record, "request_id", None) or "-"
        line = (
            f"{timestamp} | {record.levelname:<8} | {record.name} | "
            f"[{request_id}] {record.getMessage()}"
        )
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


def configure_logging(
    log_level: str = DEFAULT_LOG_LEVEL,
    log_format: str = DEFAULT_LOG_FORMAT,
) -> None:
    """Configure application logging while preserving external test handlers."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    formatter: logging.Formatter = (
        JsonFormatter() if log_format.lower() == "json" else TextFormatter()
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    taskhub_handler: logging.Handler | None = None
    for handler in root_logger.handlers:
        if getattr(handler, "_taskhub_handler", False):
            taskhub_handler = handler
            break

    if taskhub_handler is None:
        taskhub_handler = logging.StreamHandler(sys.stdout)
        taskhub_handler._taskhub_handler = True  # type: ignore[attr-defined]
        taskhub_handler.addFilter(RequestIdFilter())
        root_logger.addHandler(taskhub_handler)

    taskhub_handler.setLevel(numeric_level)
    taskhub_handler.setFormatter(formatter)
