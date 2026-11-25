from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.constants import INTERNAL_SERVER_ERROR
from app.schemas.error import ErrorResponse, ValidationErrorResponse

OPENAPI_DESCRIPTION = """
TaskHub is an asynchronous Task Management REST API built with FastAPI,
SQLAlchemy 2.x, MySQL 8, and Redis.

### Authentication
Protected endpoints require an HTTP `Authorization: Bearer <access_token>` header
obtained from `/api/v1/auth/login`.

### Request Tracing & Error Format
- All responses include `X-Request-ID` and `X-Process-Time` headers.
- Error responses (`400`, `401`, `403`, `404`, `409`, `500`) return
  `{"detail": "<message>"}`.
- Validation errors (`422`) return sanitized
  `{"detail": [{"loc": ..., "msg": ..., "type": ...}]}`.
""".strip()

OPENAPI_TAGS: list[dict[str, Any]] = [
    {"name": "Health", "description": "Service liveness and readiness checks."},
    {
        "name": "Auth",
        "description": (
            "User registration, JWT login, token refresh rotation, and logout."
        ),
    },
    {"name": "Users", "description": "Current user profile and password management."},
    {
        "name": "Workspaces",
        "description": "Workspace management and member RBAC (OWNER, EDITOR, VIEWER).",
    },
    {
        "name": "Projects",
        "description": "Project CRUD and archive lifecycle within workspaces.",
    },
    {
        "name": "Tasks",
        "description": (
            "Task CRUD, assignment notifications, filtering, pagination, and caching."
        ),
    },
    {"name": "Labels", "description": "Project label CRUD and task label assignment."},
    {"name": "Comments", "description": "Task comments with author/owner moderation."},
]

_ERROR_SCHEMA_REF = {"$ref": "#/components/schemas/ErrorResponse"}
_VALIDATION_SCHEMA_REF = {"$ref": "#/components/schemas/ValidationErrorResponse"}
_STANDARD_ERROR_CODES = ("400", "401", "403", "404", "409")


def _register_error_schemas(schemas: dict[str, Any]) -> None:
    error_schema = ErrorResponse.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    schemas["ErrorResponse"] = error_schema

    validation_schema = ValidationErrorResponse.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    defs = validation_schema.pop("$defs", {})
    for name, definition in defs.items():
        schemas.setdefault(name, definition)
    schemas["ValidationErrorResponse"] = validation_schema


def configure_openapi(application: FastAPI) -> None:
    """Configure rich OpenAPI metadata, error models, and standard responses."""

    def custom_openapi() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema

        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=OPENAPI_DESCRIPTION,
            tags=OPENAPI_TAGS,
            routes=application.routes,
        )

        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        _register_error_schemas(schemas)

        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.setdefault("responses", {})
                for code in _STANDARD_ERROR_CODES:
                    if code in responses and "content" not in responses[code]:
                        responses[code]["content"] = {
                            "application/json": {"schema": _ERROR_SCHEMA_REF}
                        }

                if "422" in responses:
                    responses["422"] = {
                        "description": "Validation Error",
                        "content": {
                            "application/json": {"schema": _VALIDATION_SCHEMA_REF}
                        },
                    }

                responses.setdefault(
                    "500",
                    {
                        "description": INTERNAL_SERVER_ERROR,
                        "content": {"application/json": {"schema": _ERROR_SCHEMA_REF}},
                    },
                )

        application.openapi_schema = schema
        return schema

    application.openapi = custom_openapi  # type: ignore[method-assign]
