from pathlib import Path

from fastapi.testclient import TestClient

from app.core.openapi import OPENAPI_TAGS
from app.main import app, create_app
from app.schemas.error import ErrorResponse, ValidationErrorResponse

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_openapi_metadata_tags_and_docs_endpoints(database_url: str) -> None:
    with TestClient(app) as client:
        docs_res = client.get("/docs")
        redoc_res = client.get("/redoc")
        schema_res = client.get("/openapi.json")

    assert docs_res.status_code == 200
    assert "swagger-ui" in docs_res.text.lower()
    assert redoc_res.status_code == 200
    assert "redoc" in redoc_res.text.lower()

    assert schema_res.status_code == 200
    schema = schema_res.json()
    assert schema["info"]["title"] == "TaskHub API"
    assert schema["info"]["version"] == "0.1.0"
    assert "Bearer" in schema["info"]["description"]

    tag_names = [tag["name"] for tag in schema["tags"]]
    assert tag_names == [tag["name"] for tag in OPENAPI_TAGS]
    assert all(tag.get("description") for tag in schema["tags"])


def test_openapi_bearer_security_scheme_and_routes() -> None:
    schema = app.openapi()
    security_schemes = schema["components"]["securitySchemes"]
    assert "BearerAuth" in security_schemes
    assert security_schemes["BearerAuth"]["type"] == "http"
    assert security_schemes["BearerAuth"]["scheme"] == "bearer"
    assert security_schemes["BearerAuth"]["bearerFormat"] == "JWT"

    public_paths = {
        "/api/v1/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    }

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if path in public_paths:
                assert "security" not in operation, f"{method} {path} should be public"
            else:
                assert operation.get("security") == [{"BearerAuth": []}], (
                    f"{method} {path} should require BearerAuth"
                )


def test_openapi_error_response_schemas_match_runtime(database_url: str) -> None:
    schema = app.openapi()
    schemas = schema["components"]["schemas"]
    assert "ErrorResponse" in schemas
    assert "ValidationErrorResponse" in schemas
    assert "ValidationErrorDetail" in schemas

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            responses = operation["responses"]
            assert "500" in responses, f"Missing 500 response on {method} {path}"
            assert responses["500"]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
            for code in ("400", "401", "403", "404", "409"):
                if code in responses:
                    assert responses[code]["content"]["application/json"]["schema"] == {
                        "$ref": "#/components/schemas/ErrorResponse"
                    }
            if "422" in responses:
                assert responses["422"]["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/ValidationErrorResponse"
                }

    with TestClient(app) as client:
        unauth_res = client.get("/api/v1/users/me")
        assert unauth_res.status_code == 401
        parsed_err = ErrorResponse.model_validate(unauth_res.json())
        assert parsed_err.detail

        val_res = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "full_name": "A", "password": "pw"},
        )
        assert val_res.status_code == 422
        parsed_val = ValidationErrorResponse.model_validate(val_res.json())
        assert len(parsed_val.detail) >= 1


def test_create_app_caches_openapi_schema() -> None:
    fresh_app = create_app()
    first = fresh_app.openapi()
    second = fresh_app.openapi()
    assert first is second


def test_docker_files_present_and_configured() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/api/v1/health" in dockerfile
    assert "uvicorn" in dockerfile

    for excluded in (".env", ".venv/", ".git/", ".cache/", "*.md"):
        assert excluded in dockerignore

    assert "mysql:8.0" in compose
    assert "redis:7-alpine" in compose
    assert "service_healthy" in compose
    assert "alembic upgrade head" in compose
    assert "uvicorn app.main:app" in compose
