from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.dependencies import get_task_repository
from app.main import app
from app.repositories.task import TaskRepository
from app.schemas.task import TaskRead


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_create_and_get_task(client: TestClient) -> None:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Learn FastAPI", "description": "Practice routing"},
    )

    assert created.status_code == 201
    task = created.json()
    assert task == {
        "id": 1,
        "title": "Learn FastAPI",
        "description": "Practice routing",
    }
    detail = client.get(f"/api/v1/tasks/{task['id']}")
    assert detail.status_code == 200
    assert detail.json() == task


def test_list_empty_store(client: TestClient) -> None:
    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_tasks_with_query_parameters(client: TestClient) -> None:
    for title in ("Read Python", "Learn FastAPI", "Test FastAPI"):
        response = client.post("/api/v1/tasks", json={"title": title})
        assert response.status_code == 201

    response = client.get("/api/v1/tasks", params={"q": "fastapi", "limit": 1})

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"id": 2, "title": "Learn FastAPI", "description": None}],
        "total": 2,
    }


def test_list_tasks_defaults_to_ten_results(client: TestClient) -> None:
    for index in range(11):
        response = client.post("/api/v1/tasks", json={"title": f"Task {index}"})
        assert response.status_code == 201

    response = client.get("/api/v1/tasks")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 11
    assert len(data["items"]) == 10


def test_list_tasks_is_sorted_by_id(client: TestClient) -> None:
    for title in ("Zebra", "Apple", "Mango"):
        client.post("/api/v1/tasks", json={"title": title})

    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    items = response.json()["items"]
    ids = [item["id"] for item in items]
    assert ids == sorted(ids)


def test_get_missing_task(client: TestClient) -> None:
    response = client.get("/api/v1/tasks/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


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
    assert client.get("/api/v1/tasks").json() == {"items": [], "total": 0}


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


# --- PUT Tests ---


def test_put_task(client: TestClient) -> None:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Original Title", "description": "Original Description"},
    ).json()

    response = client.put(
        f"/api/v1/tasks/{created['id']}",
        json={"title": "Updated Title", "description": "Updated Description"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "title": "Updated Title",
        "description": "Updated Description",
    }


def test_put_missing_task(client: TestClient) -> None:
    response = client.put(
        "/api/v1/tasks/999",
        json={"title": "Updated Title", "description": "Updated Description"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_put_rejects_missing_title(client: TestClient) -> None:
    created = client.post("/api/v1/tasks", json={"title": "Task"}).json()
    response = client.put(
        f"/api/v1/tasks/{created['id']}",
        json={"description": "No title provided"},
    )
    assert response.status_code == 422


# --- PATCH Tests ---


def test_patch_title_only(client: TestClient) -> None:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Original Title", "description": "Preserved Desc"},
    ).json()

    response = client.patch(
        f"/api/v1/tasks/{created['id']}",
        json={"title": "New Title"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "title": "New Title",
        "description": "Preserved Desc",
    }


def test_patch_description_only(client: TestClient) -> None:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Preserved Title", "description": "Old Desc"},
    ).json()

    response = client.patch(
        f"/api/v1/tasks/{created['id']}",
        json={"description": "New Desc"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "title": "Preserved Title",
        "description": "New Desc",
    }


def test_patch_description_to_null(client: TestClient) -> None:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Preserved Title", "description": "Old Desc"},
    ).json()

    response = client.patch(
        f"/api/v1/tasks/{created['id']}",
        json={"description": None},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": created["id"],
        "title": "Preserved Title",
        "description": None,
    }


def test_patch_no_op(client: TestClient) -> None:
    created = client.post("/api/v1/tasks", json={"title": "Title"}).json()
    response = client.patch(f"/api/v1/tasks/{created['id']}", json={})
    assert response.status_code == 200
    assert response.json()["title"] == "Title"


def test_patch_rejects_null_title(client: TestClient) -> None:
    created = client.post("/api/v1/tasks", json={"title": "Original"}).json()
    response = client.patch(
        f"/api/v1/tasks/{created['id']}",
        json={"title": None},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "title"]


def test_patch_missing_task(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/tasks/999",
        json={"title": "Updated"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


# --- DELETE Tests ---


def test_delete_task(client: TestClient) -> None:
    created = client.post("/api/v1/tasks", json={"title": "To Delete"}).json()

    response = client.delete(f"/api/v1/tasks/{created['id']}")
    assert response.status_code == 204

    get_response = client.get(f"/api/v1/tasks/{created['id']}")
    assert get_response.status_code == 404


def test_delete_missing_task(client: TestClient) -> None:
    response = client.delete("/api/v1/tasks/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


def test_id_is_not_reused_after_delete(client: TestClient) -> None:
    t1 = client.post("/api/v1/tasks", json={"title": "Task 1"}).json()
    t2 = client.post("/api/v1/tasks", json={"title": "Task 2"}).json()
    assert t1["id"] == 1
    assert t2["id"] == 2

    # Delete task 2
    del_res = client.delete(f"/api/v1/tasks/{t2['id']}")
    assert del_res.status_code == 204

    # Create task 3; id MUST be 3, not reusing 2!
    t3 = client.post("/api/v1/tasks", json={"title": "Task 3"}).json()
    assert t3["id"] == 3


# --- Dependency Override & Lifecycle Tests ---


def test_task_repository_dependency_can_be_overridden(client: TestClient) -> None:
    repo = TaskRepository(
        initial_tasks={42: TaskRead(id=42, title="Injected task", description=None)}
    )
    app.dependency_overrides[get_task_repository] = lambda: repo
    try:
        response = client.get("/api/v1/tasks/42")

        assert response.status_code == 200
        assert response.json()["title"] == "Injected task"
        created = client.post("/api/v1/tasks", json={"title": "Another task"})
        assert created.status_code == 201
        assert created.json()["id"] == 43
        assert repo.get(43).title == "Another task"
    finally:
        app.dependency_overrides.pop(get_task_repository)

    assert client.get("/api/v1/tasks").json() == {"items": [], "total": 0}


def test_practice_data_is_reset_when_application_restarts() -> None:
    with TestClient(app) as first_client:
        response = first_client.post("/api/v1/tasks", json={"title": "Temporary"})
        assert response.status_code == 201

    with TestClient(app) as restarted_client:
        assert restarted_client.get("/api/v1/tasks").json() == {"items": [], "total": 0}
