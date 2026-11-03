from fastapi.testclient import TestClient

from app.main import app


def test_openapi_documents_health_routes() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "TaskHub API"
    assert "get" in schema["paths"]["/health"]
    assert "get" in schema["paths"]["/api/v1/health"]


def test_swagger_ui_uses_application_schema() -> None:
    with TestClient(app) as client:
        response = client.get("/docs")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "TaskHub API - Swagger UI" in response.text
    assert "url: '/openapi.json'" in response.text


def test_redoc_uses_application_schema() -> None:
    with TestClient(app) as client:
        response = client.get("/redoc")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'spec-url="/openapi.json"' in response.text
