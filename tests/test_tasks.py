import asyncio
from collections.abc import Iterator
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.constants import DATABASE_CONFLICT
from app.core.dependencies import get_task_repository
from app.db.session import create_database_engine
from app.main import app
from app.models import Project, Task
from app.repositories.task import TaskRepository


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def create_task(client: TestClient, title: str = "Learn FastAPI", **fields) -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"title": title, "project_id": 1, "created_by": 1, **fields},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_task(client: TestClient) -> None:
    task = create_task(client, "  Learn FastAPI  ", description="Practice routing")
    assert task["title"] == "Learn FastAPI"
    assert task["description"] == "Practice routing"
    assert task["project_id"] == task["created_by"] == 1
    assert task["status"] == "TODO"
    assert task["priority"] == "MEDIUM"
    assert task["created_at"]
    assert client.get(f"/api/v1/tasks/{task['id']}").json() == task


def test_list_tasks_search_and_pagination(client: TestClient) -> None:
    for title in ("Read Python", "Learn FastAPI", "Test FastAPI"):
        create_task(client, title)
    response = client.get(
        "/api/v1/tasks", params={"q": "  FASTAPI  ", "page": 2, "limit": 1}
    )
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    assert page["page"] == 2
    assert page["limit"] == 1
    assert [task["title"] for task in page["items"]] == ["Test FastAPI"]
    beyond = client.get("/api/v1/tasks", params={"page": 10}).json()
    assert beyond["items"] == []
    assert beyond["total"] == 3


@pytest.mark.parametrize("query", ["%", "_", "' OR 1=1 --"])
def test_search_treats_sql_characters_as_literal_text(
    client: TestClient, query: str
) -> None:
    create_task(client, "Ordinary task")
    matching = create_task(client, f"Task {query}")
    page = client.get("/api/v1/tasks", params={"q": query}).json()
    assert page["total"] == 1
    assert [task["id"] for task in page["items"]] == [matching["id"]]


def test_list_empty_database(client: TestClient) -> None:
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "limit": 10}


def test_list_defaults_to_ten_results(client: TestClient) -> None:
    for index in range(11):
        create_task(client, f"Task {index}")
    page = client.get("/api/v1/tasks").json()
    assert len(page["items"]) == 10
    assert page["total"] == 11


def test_task_survives_application_restart(database_url: str) -> None:
    with TestClient(app) as client:
        task = create_task(client)
    with TestClient(app) as restarted_client:
        response = restarted_client.get(f"/api/v1/tasks/{task['id']}")
        assert response.status_code == 200
        assert response.json() == task


def test_patch_only_changes_supplied_fields(client: TestClient) -> None:
    task = create_task(client, description="Keep this")
    response = client.patch(
        f"/api/v1/tasks/{task['id']}", json={"title": "  Updated  ", "status": "DONE"}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Updated"
    assert updated["status"] == "DONE"
    assert updated["description"] == "Keep this"
    assert updated["project_id"] == task["project_id"]
    assert client.patch(f"/api/v1/tasks/{task['id']}", json={}).json() == updated


@pytest.mark.parametrize("field", ["title", "status", "priority"])
def test_patch_rejects_null_without_corrupting_data(
    client: TestClient, field: str
) -> None:
    task = create_task(client)
    response = client.patch(f"/api/v1/tasks/{task['id']}", json={field: None})
    assert response.status_code == 422
    assert client.get(f"/api/v1/tasks/{task['id']}").json() == task
    page = client.get("/api/v1/tasks")
    assert page.status_code == 200
    assert page.json()["items"] == [task]


def test_patch_allows_clearing_nullable_fields(client: TestClient) -> None:
    task = create_task(
        client, description="Clear me", assignee_id=2, due_date="2026-12-01T12:00:00"
    )
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"description": None, "assignee_id": None, "due_date": None},
    )
    assert response.status_code == 200
    assert all(
        response.json()[field] is None
        for field in ("description", "assignee_id", "due_date")
    )


def test_delete_task(client: TestClient) -> None:
    task = create_task(client)
    response = client.delete(f"/api/v1/tasks/{task['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/v1/tasks/{task['id']}").status_code == 404
    assert client.get("/api/v1/tasks").json()["total"] == 0


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_missing_task_returns_consistent_404(client: TestClient, method: str) -> None:
    response = client.request(
        method, "/api/v1/tasks/999", **({"json": {}} if method == "patch" else {})
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}


@pytest.mark.parametrize(
    "fields", [{"project_id": 999}, {"created_by": 999}, {"assignee_id": 999}]
)
def test_create_rejects_missing_related_records(
    client: TestClient, fields: dict
) -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"title": "Task", "project_id": 1, "created_by": 1, **fields},
    )
    assert response.status_code == 404
    assert client.get("/api/v1/tasks").json()["total"] == 0


@pytest.mark.parametrize(
    "fields",
    [
        {"title": None},
        {"title": ""},
        {"title": "   "},
        {"title": 123},
        {"title": "x" * 201},
        {"description": "x" * 2001},
        {"description": 123},
        {"id": 99},
        {"project_id": 0},
        {"created_by": 0},
        {"status": "INVALID"},
    ],
)
def test_reject_invalid_create_body(client: TestClient, fields: dict) -> None:
    response = client.post(
        "/api/v1/tasks",
        json={"title": "Task", "project_id": 1, "created_by": 1, **fields},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/tasks").json()["total"] == 0


@pytest.mark.parametrize("payload", [{}, {"title": "Missing references"}])
def test_reject_incomplete_create_body(client: TestClient, payload: dict) -> None:
    assert client.post("/api/v1/tasks", json=payload).status_code == 422


@pytest.mark.parametrize("task_id", ["0", "-1", "abc", "1.5"])
def test_reject_invalid_path_parameter(client: TestClient, task_id: str) -> None:
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "abc"},
        {"page": "0"},
        {"page": "-1"},
        {"page": "abc"},
        {"q": ""},
        {"q": "   "},
        {"q": "x" * 201},
        {"project_id": "0"},
    ],
)
def test_reject_invalid_query_parameters(client: TestClient, params: dict) -> None:
    response = client.get("/api/v1/tasks", params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   "},
        {"title": "x" * 201},
        {"status": "INVALID"},
        {"priority": "INVALID"},
        {"project_id": 2},
        {"created_by": 2},
        {"id": 42},
        {"description": "x" * 2001},
    ],
)
def test_invalid_patch_preserves_existing_data(
    client: TestClient, payload: dict
) -> None:
    task = create_task(client)
    assert client.patch(f"/api/v1/tasks/{task['id']}", json=payload).status_code == 422
    assert client.get(f"/api/v1/tasks/{task['id']}").json() == task


def test_missing_assignee_does_not_partially_update_task(client: TestClient) -> None:
    task = create_task(client)
    response = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"title": "Should not change", "assignee_id": 999},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Assignee not found"}
    assert client.get(f"/api/v1/tasks/{task['id']}").json() == task


def test_accept_length_boundaries_and_normalize_due_date(client: TestClient) -> None:
    task = create_task(
        client,
        "x" * 200,
        description="x" * 2000,
        due_date="2026-12-01T12:00:00+07:00",
    )
    assert len(task["title"]) == 200
    assert len(task["description"]) == 2000
    assert task["due_date"] == "2026-12-01T05:00:00"


def test_repository_dependency_can_be_overridden(client: TestClient) -> None:
    repository = AsyncMock(spec=TaskRepository)
    repository.get.return_value = Task(
        id=42,
        title="Injected task",
        project_id=1,
        created_by=1,
        status="TODO",
        priority="MEDIUM",
        created_at=datetime(2026, 11, 6),
    )
    repository.project_exists.return_value = True
    repository.user_exists.return_value = True

    def create_in_injected_repository(task: Task) -> Task:
        task.id = 43
        task.created_at = datetime(2026, 11, 6)
        return task

    repository.create.side_effect = create_in_injected_repository
    app.dependency_overrides[get_task_repository] = lambda: repository
    try:
        response = client.get("/api/v1/tasks/42")
        assert response.status_code == 200
        assert response.json()["title"] == "Injected task"
        assert create_task(client, "Injected create")["id"] == 43
    finally:
        app.dependency_overrides.pop(get_task_repository)
    assert client.get("/api/v1/tasks/42").status_code == 404
    assert client.get("/api/v1/tasks").json()["total"] == 0


def test_filter_tasks_by_project(client: TestClient, database_url: str) -> None:
    async def add_second_project() -> int:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                project = Project(workspace_id=1, name="Second project")
                session.add(project)
                await session.flush()
                return project.id
        finally:
            await engine.dispose()

    second_project_id = asyncio.run(add_second_project())
    expected = create_task(client, "First project task")
    create_task(client, "Second project task", project_id=second_project_id)

    page = client.get("/api/v1/tasks", params={"project_id": 1}).json()
    assert page["total"] == 1
    assert [task["id"] for task in page["items"]] == [expected["id"]]
    assert client.get("/api/v1/tasks", params={"project_id": 999}).json()["total"] == 0


def test_foreign_key_conflict_is_safe_and_rolls_back(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TaskRepository, "user_exists", AsyncMock(return_value=True))
    response = client.post(
        "/api/v1/tasks",
        json={"title": "Invalid reference", "project_id": 1, "created_by": 999},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": DATABASE_CONFLICT}
    assert client.get("/api/v1/tasks").json()["total"] == 0
    create_task(client, "Valid after rollback")


def test_invalid_response_is_not_returned_to_client(database_url: str) -> None:
    repository = AsyncMock(spec=TaskRepository)
    repository.get.return_value = {"id": 1, "description": "Missing title"}
    app.dependency_overrides[get_task_repository] = lambda: repository
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/v1/tasks/1")
        assert response.status_code == 500
        assert response.text == "Internal Server Error"
    finally:
        app.dependency_overrides.pop(get_task_repository)
