import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.constants import (
    ASSIGNEE_NOT_FOUND,
    ASSIGNEE_NOT_WORKSPACE_MEMBER,
    PROJECT_ARCHIVED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
)
from app.core.security import create_access_token
from app.db.session import create_database_engine
from app.main import app
from app.models import Project, User, Workspace, WorkspaceMember
from app.models.enums import (
    ProjectStatus,
    TaskPriority,
    TaskStatus,
    UserRole,
    WorkspaceRole,
)
from tests.conftest import TEST_JWT_SECRET, TEST_PASSWORD_HASH


def auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=user_id, secret_key=TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def setup_workspace_roles(database_url: str) -> None:
    """Create platform ADMIN (3), workspace EDITOR (4), workspace VIEWER (5), and a second workspace."""

    async def _setup() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                admin = User(
                    id=3,
                    email="admin@example.com",
                    full_name="Platform Admin",
                    hashed_password=TEST_PASSWORD_HASH,
                    role=UserRole.ADMIN,
                )
                editor = User(
                    id=4,
                    email="editor@example.com",
                    full_name="Workspace Editor",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                viewer = User(
                    id=5,
                    email="viewer@example.com",
                    full_name="Workspace Viewer",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                other_ws = Workspace(id=2, name="Other Workspace", owner_id=2)
                other_ws.members.append(
                    WorkspaceMember(user_id=2, role=WorkspaceRole.OWNER)
                )
                other_project = Project(id=2, name="Other Project", workspace=other_ws)
                session.add_all([admin, editor, viewer, other_project])
                await session.flush()

                session.add_all(
                    [
                        WorkspaceMember(
                            workspace_id=1, user_id=4, role=WorkspaceRole.EDITOR
                        ),
                        WorkspaceMember(
                            workspace_id=1, user_id=5, role=WorkspaceRole.VIEWER
                        ),
                    ]
                )
        finally:
            await engine.dispose()

    asyncio.run(_setup())


def test_nested_project_tasks_create_and_list(
    client: TestClient, setup_workspace_roles: None
) -> None:
    # Missing project -> 404
    assert (
        client.post(
            "/api/v1/projects/999/tasks",
            headers=auth_headers(1),
            json={"title": "Missing project"},
        ).status_code
        == 404
    )
    res_list_404 = client.get("/api/v1/projects/999/tasks", headers=auth_headers(1))
    assert res_list_404.status_code == 404
    assert res_list_404.json() == {"detail": PROJECT_NOT_FOUND}

    # Extra forbidden field (e.g. project_id in body of nested route) -> 422
    assert (
        client.post(
            "/api/v1/projects/1/tasks",
            headers=auth_headers(1),
            json={"title": "Extra field", "project_id": 1},
        ).status_code
        == 422
    )

    # Editor creates task via nested route with status, priority, assignee, due_date
    res = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(4),
        json={
            "title": "  Implement filtering  ",
            "description": "Support status and priority filters",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": TaskPriority.HIGH.value,
            "assignee_id": 4,
            "due_date": "2026-12-15T17:00:00+07:00",
        },
    )
    assert res.status_code == 201, res.text
    task = res.json()
    assert task["project_id"] == 1
    assert task["created_by"] == 4
    assert task["assignee_id"] == 4
    assert task["title"] == "Implement filtering"
    assert task["status"] == TaskStatus.IN_PROGRESS.value
    assert task["priority"] == TaskPriority.HIGH.value
    assert task["due_date"] == "2026-12-15T10:00:00Z"

    # Viewer lists nested project tasks -> 200
    list_res = client.get("/api/v1/projects/1/tasks", headers=auth_headers(5))
    assert list_res.status_code == 200
    page = list_res.json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == task["id"]


def test_task_rbac_and_workspace_isolation(
    client: TestClient, setup_workspace_roles: None
) -> None:
    # Owner creates a task in project 1
    task = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "WS1 Task"},
    ).json()
    task_id = task["id"]

    # User 2 creates a task in workspace 2 / project 2
    other_task = client.post(
        "/api/v1/projects/2/tasks",
        headers=auth_headers(2),
        json={"title": "WS2 Task"},
    ).json()

    # Non-member (user 2) gets 403 on workspace 1 / project 1 / task 1
    assert (
        client.post(
            "/api/v1/projects/1/tasks",
            headers=auth_headers(2),
            json={"title": "Sneak"},
        ).status_code
        == 403
    )
    res_post_flat = client.post(
        "/api/v1/tasks",
        headers=auth_headers(2),
        json={"title": "Sneak", "project_id": 1},
    )
    assert res_post_flat.status_code == 403
    assert res_post_flat.json() == {"detail": PROJECT_FORBIDDEN}

    assert (
        client.get("/api/v1/projects/1/tasks", headers=auth_headers(2)).status_code
        == 403
    )

    res_get = client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers(2))
    assert res_get.status_code == 403
    assert res_get.json() == {"detail": TASK_FORBIDDEN}

    assert (
        client.patch(
            f"/api/v1/tasks/{task_id}",
            headers=auth_headers(2),
            json={"title": "Hacked"},
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers(2)).status_code
        == 403
    )

    # /api/v1/tasks only returns tasks from user's workspaces
    u2_tasks = client.get("/api/v1/tasks", headers=auth_headers(2)).json()
    assert [t["id"] for t in u2_tasks["items"]] == [other_task["id"]]

    u1_tasks = client.get("/api/v1/tasks", headers=auth_headers(1)).json()
    assert [t["id"] for t in u1_tasks["items"]] == [task_id]

    # Viewer (user 5) can read but gets 403 on create/patch/delete
    assert (
        client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers(5)).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/projects/1/tasks",
            headers=auth_headers(5),
            json={"title": "Viewer Task"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/tasks/{task_id}",
            headers=auth_headers(5),
            json={"status": TaskStatus.DONE.value},
        ).status_code
        == 403
    )
    assert (
        client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers(5)).status_code
        == 403
    )

    # Editor (user 4) can update and delete tasks
    patch_res = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(4),
        json={"status": TaskStatus.IN_REVIEW.value},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == TaskStatus.IN_REVIEW.value

    # Platform ADMIN (user 3) sees all workspaces and can mutate/delete
    admin_list = client.get("/api/v1/tasks", headers=auth_headers(3)).json()
    assert admin_list["total"] == 2
    assert (
        client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers(3)).status_code
        == 204
    )


def test_assignee_must_be_workspace_member(
    client: TestClient, setup_workspace_roles: None
) -> None:
    # Non-existent user -> 404
    res_404 = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Missing assignee", "assignee_id": 999},
    )
    assert res_404.status_code == 404
    assert res_404.json() == {"detail": ASSIGNEE_NOT_FOUND}

    # Existing user (user 2) who is NOT a member of workspace 1 -> 400 on create
    res_400 = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Non-member assignee", "assignee_id": 2},
    )
    assert res_400.status_code == 400
    assert res_400.json() == {"detail": ASSIGNEE_NOT_WORKSPACE_MEMBER}

    # Create valid task assigned to viewer (user 5) - workspace members can be assigned
    task = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Assigned task", "assignee_id": 5},
    ).json()
    assert task["assignee_id"] == 5

    # Assigning non-member on PATCH -> 400 and preserves existing assignee
    res_patch_400 = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers(1),
        json={"assignee_id": 2},
    )
    assert res_patch_400.status_code == 400
    assert res_patch_400.json() == {"detail": ASSIGNEE_NOT_WORKSPACE_MEMBER}
    assert (
        client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers(1)).json()[
            "assignee_id"
        ]
        == 5
    )

    # Re-assigning to editor (user 4) -> 200
    res_patch_ok = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers(1),
        json={"assignee_id": 4},
    )
    assert res_patch_ok.status_code == 200
    assert res_patch_ok.json()["assignee_id"] == 4


def test_archived_project_rejects_task_mutations(
    client: TestClient, setup_workspace_roles: None
) -> None:
    task = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Before archive"},
    ).json()

    # Archive project 1
    assert (
        client.patch(
            "/api/v1/projects/1",
            headers=auth_headers(1),
            json={"status": ProjectStatus.ARCHIVED.value},
        ).status_code
        == 200
    )

    # Reading still works
    assert (
        client.get("/api/v1/projects/1/tasks", headers=auth_headers(5)).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/tasks/{task['id']}", headers=auth_headers(5)).status_code
        == 200
    )

    # Create/Update/Delete rejected with 400 PROJECT_ARCHIVED
    res_create = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "After archive"},
    )
    assert res_create.status_code == 400
    assert res_create.json() == {"detail": PROJECT_ARCHIVED}

    res_patch = client.patch(
        f"/api/v1/tasks/{task['id']}",
        headers=auth_headers(1),
        json={"status": TaskStatus.DONE.value},
    )
    assert res_patch.status_code == 400
    assert res_patch.json() == {"detail": PROJECT_ARCHIVED}

    res_delete = client.delete(f"/api/v1/tasks/{task['id']}", headers=auth_headers(1))
    assert res_delete.status_code == 400
    assert res_delete.json() == {"detail": PROJECT_ARCHIVED}


def test_update_status_priority_due_date_and_filtering(
    client: TestClient, setup_workspace_roles: None
) -> None:
    t1 = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={
            "title": "Alpha bug fix",
            "status": TaskStatus.TODO.value,
            "priority": TaskPriority.URGENT.value,
            "assignee_id": 1,
        },
    ).json()
    t2 = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={
            "title": "Beta feature work",
            "status": TaskStatus.IN_PROGRESS.value,
            "priority": TaskPriority.HIGH.value,
            "assignee_id": 4,
        },
    ).json()
    t3 = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(4),
        json={
            "title": "Gamma bug polish",
            "status": TaskStatus.DONE.value,
            "priority": TaskPriority.LOW.value,
            "assignee_id": 4,
        },
    ).json()

    # Transition t1 status & priority & due_date
    patched = client.patch(
        f"/api/v1/tasks/{t1['id']}",
        headers=auth_headers(1),
        json={
            "status": TaskStatus.IN_REVIEW.value,
            "priority": TaskPriority.MEDIUM.value,
            "due_date": "2026-12-20T09:30:00Z",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == TaskStatus.IN_REVIEW.value
    assert patched.json()["priority"] == TaskPriority.MEDIUM.value
    assert patched.json()["due_date"] == "2026-12-20T09:30:00Z"

    # Filter by status
    res_status = client.get(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(5),
        params={"status": "IN_PROGRESS"},
    ).json()
    assert [t["id"] for t in res_status["items"]] == [t2["id"]]

    # Filter by priority
    res_priority = client.get(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(5),
        params={"priority": "LOW"},
    ).json()
    assert [t["id"] for t in res_priority["items"]] == [t3["id"]]

    # Filter by assignee_id + search q
    res_combo = client.get(
        "/api/v1/tasks",
        headers=auth_headers(4),
        params={"assignee_id": 4, "q": "bug"},
    ).json()
    assert [t["id"] for t in res_combo["items"]] == [t3["id"]]

    # Pagination on assignee_id=4 (t2 and t3)
    res_page2 = client.get(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(4),
        params={"assignee_id": 4, "page": 2, "limit": 1},
    ).json()
    assert res_page2["total"] == 2
    assert res_page2["page"] == 2
    assert res_page2["limit"] == 1
    assert [t["id"] for t in res_page2["items"]] == [t3["id"]]

    # Invalid filter query params -> 422
    for bad_params in (
        {"status": "UNKNOWN"},
        {"priority": "CRITICAL"},
        {"assignee_id": "0"},
    ):
        assert (
            client.get(
                "/api/v1/projects/1/tasks",
                headers=auth_headers(1),
                params=bad_params,
            ).status_code
            == 422
        )
