from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_not_mounted_at_root() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 404
