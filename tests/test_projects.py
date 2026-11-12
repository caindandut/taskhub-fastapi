from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.constants import (
    NOT_AUTHENTICATED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    WORKSPACE_FORBIDDEN,
    WORKSPACE_NOT_FOUND,
)
from app.core.security import create_access_token
from app.db.session import create_database_engine
from app.main import app
from app.models import Project, Task, User, WorkspaceMember
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from tests.conftest import TEST_JWT_SECRET, TEST_PASSWORD_HASH


def auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=user_id, secret_key=TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def setup_roles(database_url: str) -> None:
    """Setup users with different workspace roles and platform ADMIN."""
    import asyncio

    async def _setup() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                admin_user = User(
                    id=3,
                    email="admin@example.com",
                    full_name="Platform Admin",
                    hashed_password=TEST_PASSWORD_HASH,
                    role=UserRole.ADMIN,
                )
                editor_user = User(
                    id=4,
                    email="editor@example.com",
                    full_name="Workspace Editor",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                viewer_user = User(
                    id=5,
                    email="viewer@example.com",
                    full_name="Workspace Viewer",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                session.add_all([admin_user, editor_user, viewer_user])
                await session.flush()

                editor_member = WorkspaceMember(
                    workspace_id=1, user_id=4, role=WorkspaceRole.EDITOR
                )
                viewer_member = WorkspaceMember(
                    workspace_id=1, user_id=5, role=WorkspaceRole.VIEWER
                )
                session.add_all([editor_member, viewer_member])
        finally:
            await engine.dispose()

    asyncio.run(_setup())


# 1. Unauthenticated tests
def test_unauthenticated_project_endpoints(client: TestClient) -> None:
    for method, path in (
        ("post", "/api/v1/workspaces/1/projects"),
        ("get", "/api/v1/workspaces/1/projects"),
        ("get", "/api/v1/projects/1"),
        ("patch", "/api/v1/projects/1"),
        ("delete", "/api/v1/projects/1"),
    ):
        res = getattr(client, method)(path)
        assert res.status_code == 401
        assert res.json() == {"detail": NOT_AUTHENTICATED}
        assert res.headers.get("WWW-Authenticate") == "Bearer"


# 2. Validation tests
def test_create_project_validation(client: TestClient) -> None:
    # Empty name
    res = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        json={"name": "   "},
    )
    assert res.status_code == 422

    # Name too long
    res = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        json={"name": "x" * 101},
    )
    assert res.status_code == 422

    # Extra forbidden field
    res = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        json={"name": "Valid Name", "extra_field": "disallowed"},
    )
    assert res.status_code == 422


def test_update_project_validation(client: TestClient) -> None:
    # Empty name
    res = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(1),
        json={"name": "   "},
    )
    assert res.status_code == 422

    # Invalid status
    res = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(1),
        json={"status": "INVALID_STATUS"},
    )
    assert res.status_code == 422

    # Extra forbidden field
    res = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(1),
        json={"workspace_id": 2},
    )
    assert res.status_code == 422


# 3. Not found tests
def test_project_not_found(client: TestClient) -> None:
    # Workspace not found on create
    res = client.post(
        "/api/v1/workspaces/999/projects",
        headers=auth_headers(1),
        json={"name": "New Project"},
    )
    assert res.status_code == 404
    assert res.json() == {"detail": WORKSPACE_NOT_FOUND}

    # Workspace not found on list
    res = client.get(
        "/api/v1/workspaces/999/projects",
        headers=auth_headers(1),
    )
    assert res.status_code == 404
    assert res.json() == {"detail": WORKSPACE_NOT_FOUND}

    # Project not found on get
    res = client.get("/api/v1/projects/999", headers=auth_headers(1))
    assert res.status_code == 404
    assert res.json() == {"detail": PROJECT_NOT_FOUND}

    # Project not found on patch
    res = client.patch(
        "/api/v1/projects/999",
        headers=auth_headers(1),
        json={"name": "Updated"},
    )
    assert res.status_code == 404
    assert res.json() == {"detail": PROJECT_NOT_FOUND}

    # Project not found on delete
    res = client.delete("/api/v1/projects/999", headers=auth_headers(1))
    assert res.status_code == 404
    assert res.json() == {"detail": PROJECT_NOT_FOUND}


# 4. Project CRUD and RBAC tests
def test_create_project_rbac(client: TestClient, setup_roles: None) -> None:
    # Non-member (user 2) gets 403
    res_non_member = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(2),
        json={"name": "Hacked Project"},
    )
    assert res_non_member.status_code == 403
    assert res_non_member.json() == {"detail": WORKSPACE_FORBIDDEN}

    # Viewer (user 5) gets 403
    res_viewer = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(5),
        json={"name": "Viewer Project"},
    )
    assert res_viewer.status_code == 403
    assert res_viewer.json() == {"detail": PROJECT_FORBIDDEN}

    # Editor (user 4) can create project
    res_editor = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(4),
        json={"name": "  Editor Project  ", "description": "  Built by editor  "},
    )
    assert res_editor.status_code == 201
    data_editor = res_editor.json()
    assert data_editor["name"] == "Editor Project"
    assert data_editor["description"] == "Built by editor"
    assert data_editor["workspace_id"] == 1
    assert data_editor["status"] == ProjectStatus.ACTIVE.value
    assert data_editor["id"] > 0
    assert data_editor["created_at"]

    # Owner (user 1) can create project
    res_owner = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        json={"name": "Owner Project"},
    )
    assert res_owner.status_code == 201
    assert res_owner.json()["name"] == "Owner Project"


def test_list_projects_rbac_and_filters(client: TestClient, setup_roles: None) -> None:
    # Non-member (user 2) gets 403
    res_non_member = client.get(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(2),
    )
    assert res_non_member.status_code == 403
    assert res_non_member.json() == {"detail": WORKSPACE_FORBIDDEN}

    # Viewer (user 5) can list projects
    res_viewer = client.get(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(5),
    )
    assert res_viewer.status_code == 200
    projects = res_viewer.json()
    assert isinstance(projects, list)
    assert len(projects) >= 1
    assert any(p["name"] == "Backend" for p in projects)

    # Archive one project
    client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(1),
        json={"status": ProjectStatus.ARCHIVED.value},
    )

    # Filter status=ACTIVE
    res_active = client.get(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        params={"status": "ACTIVE"},
    )
    assert res_active.status_code == 200
    assert all(p["status"] == "ACTIVE" for p in res_active.json())

    # Filter status=ARCHIVED
    res_archived = client.get(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        params={"status": "ARCHIVED"},
    )
    assert res_archived.status_code == 200
    assert any(p["id"] == 1 and p["status"] == "ARCHIVED" for p in res_archived.json())


def test_get_project_rbac(client: TestClient, setup_roles: None) -> None:
    # Non-member (user 2) gets 403
    res_non_member = client.get("/api/v1/projects/1", headers=auth_headers(2))
    assert res_non_member.status_code == 403
    assert res_non_member.json() == {"detail": PROJECT_FORBIDDEN}

    # Viewer (user 5) gets 200
    res_viewer = client.get("/api/v1/projects/1", headers=auth_headers(5))
    assert res_viewer.status_code == 200
    assert res_viewer.json()["name"] == "Backend"

    # Editor (user 4) gets 200
    res_editor = client.get("/api/v1/projects/1", headers=auth_headers(4))
    assert res_editor.status_code == 200

    # Owner (user 1) gets 200
    res_owner = client.get("/api/v1/projects/1", headers=auth_headers(1))
    assert res_owner.status_code == 200


def test_update_project_and_archive_rbac(client: TestClient, setup_roles: None) -> None:
    # Non-member (user 2) gets 403
    res_non_member = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(2),
        json={"name": "Hacked"},
    )
    assert res_non_member.status_code == 403
    assert res_non_member.json() == {"detail": PROJECT_FORBIDDEN}

    # Viewer (user 5) gets 403
    res_viewer = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(5),
        json={"name": "Viewer Edit"},
    )
    assert res_viewer.status_code == 403
    assert res_viewer.json() == {"detail": PROJECT_FORBIDDEN}

    # Editor (user 4) updates name and description
    res_editor = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(4),
        json={"name": "Backend v2", "description": "Updated backend service"},
    )
    assert res_editor.status_code == 200
    assert res_editor.json()["name"] == "Backend v2"
    assert res_editor.json()["description"] == "Updated backend service"

    # Editor archives project
    res_archive = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(4),
        json={"status": ProjectStatus.ARCHIVED.value},
    )
    assert res_archive.status_code == 200
    assert res_archive.json()["status"] == ProjectStatus.ARCHIVED.value

    # Owner unarchives project
    res_unarchive = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(1),
        json={"status": ProjectStatus.ACTIVE.value},
    )
    assert res_unarchive.status_code == 200
    assert res_unarchive.json()["status"] == ProjectStatus.ACTIVE.value

    # Update with empty body returns project unchanged
    res_empty = client.patch(
        "/api/v1/projects/1",
        headers=auth_headers(1),
        json={},
    )
    assert res_empty.status_code == 200
    assert res_empty.json()["name"] == "Backend v2"


def test_delete_project_rbac(client: TestClient, setup_roles: None) -> None:
    # Create a project to test deletion
    proj = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        json={"name": "To Be Deleted"},
    ).json()
    proj_id = proj["id"]

    # Non-member (user 2) gets 403
    assert (
        client.delete(
            f"/api/v1/projects/{proj_id}", headers=auth_headers(2)
        ).status_code
        == 403
    )

    # Viewer (user 5) gets 403
    assert (
        client.delete(
            f"/api/v1/projects/{proj_id}", headers=auth_headers(5)
        ).status_code
        == 403
    )

    # Editor (user 4) gets 403
    assert (
        client.delete(
            f"/api/v1/projects/{proj_id}", headers=auth_headers(4)
        ).status_code
        == 403
    )

    # Owner (user 1) deletes project successfully
    del_res = client.delete(f"/api/v1/projects/{proj_id}", headers=auth_headers(1))
    assert del_res.status_code == 204
    assert del_res.text == ""

    # Subsequent GET returns 404
    assert (
        client.get(f"/api/v1/projects/{proj_id}", headers=auth_headers(1)).status_code
        == 404
    )


def test_admin_superuser_project_access(client: TestClient, setup_roles: None) -> None:
    # Admin (user 3) is NOT a member of workspace 1
    # But admin can perform all actions
    # 1. Create project
    create_res = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(3),
        json={"name": "Admin Project"},
    )
    assert create_res.status_code == 201
    proj_id = create_res.json()["id"]

    # 2. List projects
    list_res = client.get(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(3),
    )
    assert list_res.status_code == 200
    assert any(p["id"] == proj_id for p in list_res.json())

    # 3. Get project
    get_res = client.get(
        f"/api/v1/projects/{proj_id}",
        headers=auth_headers(3),
    )
    assert get_res.status_code == 200

    # 4. Patch project
    patch_res = client.patch(
        f"/api/v1/projects/{proj_id}",
        headers=auth_headers(3),
        json={"name": "Admin Renamed", "status": ProjectStatus.ARCHIVED.value},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Admin Renamed"
    assert patch_res.json()["status"] == ProjectStatus.ARCHIVED.value

    # 5. Delete project
    del_res = client.delete(
        f"/api/v1/projects/{proj_id}",
        headers=auth_headers(3),
    )
    assert del_res.status_code == 204


def test_cascade_delete_tasks_when_project_deleted(
    client: TestClient, database_url: str
) -> None:
    import asyncio

    # Create a project and add a task to it
    proj = client.post(
        "/api/v1/workspaces/1/projects",
        headers=auth_headers(1),
        json={"name": "Cascade Test Project"},
    ).json()
    proj_id = proj["id"]

    # Create task under this project
    task = client.post(
        "/api/v1/tasks",
        headers=auth_headers(1),
        json={"title": "Cascade Task", "project_id": proj_id},
    ).json()
    task_id = task["id"]

    # Verify task exists
    assert (
        client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers(1)).status_code
        == 200
    )

    # Delete project
    assert (
        client.delete(
            f"/api/v1/projects/{proj_id}", headers=auth_headers(1)
        ).status_code
        == 204
    )

    # Verify project is gone
    assert (
        client.get(f"/api/v1/projects/{proj_id}", headers=auth_headers(1)).status_code
        == 404
    )

    # Verify task is cascade deleted
    async def _verify_task_deleted() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                assert await session.get(Task, task_id) is None
                assert await session.get(Project, proj_id) is None
        finally:
            await engine.dispose()

    asyncio.run(_verify_task_deleted())
