from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_task_store
from app.main import app
from app.schemas.task import TaskRead


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_create_and_get_task(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"title": "  Learn FastAPI  ", "description": "Practice routing"},
    )

    assert response.status_code == 201
    task = response.json()
    assert task == {
        "id": 1,
        "title": "Learn FastAPI",
        "description": "Practice routing",
    }
    detail = client.get(f"/api/v1/tasks/{task['id']}")
    assert detail.status_code == 200
    assert detail.json() == task


def test_list_tasks_with_query_parameters(client: TestClient) -> None:
    for title in ("Read Python", "Learn FastAPI", "Test FastAPI"):
        response = client.post("/api/v1/tasks", json={"title": title})
        assert response.status_code == 201

    response = client.get("/api/v1/tasks", params={"q": "fastapi", "limit": 1})

    assert response.status_code == 200
    assert response.json() == [{"id": 2, "title": "Learn FastAPI", "description": None}]


def test_get_missing_task(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_list_empty_store(client: TestClient) -> None:
    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    assert response.json() == []


def test_list_tasks_defaults_to_ten_results(client: TestClient) -> None:
    for index in range(11):
        response = client.post("/api/v1/tasks", json={"title": f"Task {index}"})
        assert response.status_code == 201

    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    assert len(response.json()) == 10


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": 123},
        {"title": "x" * 201},
        {"title": "Valid title", "description": "x" * 2001},
        {"title": "Valid title", "description": 123},
        {"title": "Valid title", "id": 99},
    ],
)
def test_reject_invalid_body(client: TestClient, payload: dict[str, object]) -> None:
    response = client.post("/api/v1/tasks", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "body"
    assert client.get("/api/v1/tasks").json() == []


def test_reject_missing_body(client: TestClient) -> None:
    response = client.post("/api/v1/tasks")

    assert response.status_code == 422


def test_accept_body_at_length_limits(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tasks", json={"title": "x" * 200, "description": "x" * 2000}
    )

    assert response.status_code == 201
    assert len(response.json()["title"]) == 200
    assert len(response.json()["description"]) == 2000


@pytest.mark.parametrize("task_id", ["0", "-1", "abc", "1.5"])
def test_reject_invalid_path_parameter(client: TestClient, task_id: str) -> None:
    response = client.get(f"/api/v1/tasks/{task_id}")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "task_id"]


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "abc"},
        {"q": ""},
        {"q": "x" * 201},
    ],
)
def test_reject_invalid_query_parameters(
    client: TestClient, params: dict[str, str]
) -> None:
    response = client.get("/api/v1/tasks", params=params)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][0] == "query"


def test_task_store_dependency_can_be_overridden(client: TestClient) -> None:
    store = {42: TaskRead(id=42, title="Injected task")}
    app.dependency_overrides[get_task_store] = lambda: store
    try:
        response = client.get("/api/v1/tasks/42")

        assert response.status_code == 200
        assert response.json()["title"] == "Injected task"
        created = client.post("/api/v1/tasks", json={"title": "Another task"})
        assert created.status_code == 201
        assert created.json()["id"] == 43
        assert store[43].title == "Another task"
    finally:
        app.dependency_overrides.pop(get_task_store)

    assert client.get("/api/v1/tasks").json() == []


def test_invalid_response_data_is_not_returned_to_client() -> None:
    app.dependency_overrides[get_task_store] = lambda: {
        1: {"id": 1, "description": "Missing required title"}
    }
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/tasks/1")
        assert response.status_code == 500
        assert response.text == "Internal Server Error"
    finally:
        app.dependency_overrides.pop(get_task_store)


def test_practice_data_is_reset_when_application_restarts() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/tasks", json={"title": "Temporary"})
        assert response.status_code == 201

    with TestClient(app) as restarted_client:
        assert restarted_client.get("/api/v1/tasks").json() == []
