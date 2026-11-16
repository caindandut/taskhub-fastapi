import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.constants import (
    COMMENT_FORBIDDEN,
    COMMENT_NOT_FOUND,
    DEFAULT_LABEL_COLOR,
    LABEL_ALREADY_ATTACHED,
    LABEL_ALREADY_EXISTS,
    LABEL_DIFFERENT_PROJECT,
    LABEL_FORBIDDEN,
    LABEL_NOT_FOUND,
    NOT_AUTHENTICATED,
    PROJECT_ARCHIVED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
    TASK_LABEL_NOT_FOUND,
    TASK_NOT_FOUND,
)
from app.core.security import create_access_token
from app.db.session import create_database_engine
from app.main import app
from app.models import Project, Task, User, Workspace, WorkspaceMember
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
def setup_data(database_url: str) -> dict[str, int]:
    """Seed admin (3), editor1 (4), editor2 (5), viewer (6), a second project in WS1, a second workspace/project, and tasks."""

    async def _setup() -> dict[str, int]:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                admin = User(
                    id=3,
                    email="admin@example.com",
                    full_name="Admin",
                    hashed_password=TEST_PASSWORD_HASH,
                    role=UserRole.ADMIN,
                )
                editor1 = User(
                    id=4,
                    email="editor1@example.com",
                    full_name="Editor One",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                editor2 = User(
                    id=5,
                    email="editor2@example.com",
                    full_name="Editor Two",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                viewer = User(
                    id=6,
                    email="viewer@example.com",
                    full_name="Viewer",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                ws1_proj2 = Project(id=2, workspace_id=1, name="Frontend")
                ws2 = Workspace(id=2, name="Other Workspace", owner_id=2)
                ws2.members.append(WorkspaceMember(user_id=2, role=WorkspaceRole.OWNER))
                ws2_proj = Project(id=3, workspace=ws2, name="External Project")

                session.add_all([admin, editor1, editor2, viewer, ws1_proj2, ws2_proj])
                await session.flush()

                session.add_all(
                    [
                        WorkspaceMember(
                            workspace_id=1, user_id=4, role=WorkspaceRole.EDITOR
                        ),
                        WorkspaceMember(
                            workspace_id=1, user_id=5, role=WorkspaceRole.EDITOR
                        ),
                        WorkspaceMember(
                            workspace_id=1, user_id=6, role=WorkspaceRole.VIEWER
                        ),
                    ]
                )
                t1 = Task(project_id=1, title="Task in P1", created_by=1)
                t2 = Task(project_id=2, title="Task in P2", created_by=1)
                session.add_all([t1, t2])
                await session.flush()
                return {"task1_id": t1.id, "task2_id": t2.id}
        finally:
            await engine.dispose()

    return asyncio.run(_setup())


def test_unauthenticated_label_and_comment_endpoints(client: TestClient) -> None:
    for method, path, payload in (
        ("post", "/api/v1/projects/1/labels", {"name": "Bug"}),
        ("get", "/api/v1/projects/1/labels", None),
        ("patch", "/api/v1/labels/1", {"name": "Bug"}),
        ("delete", "/api/v1/labels/1", None),
        ("get", "/api/v1/tasks/1/labels", None),
        ("post", "/api/v1/tasks/1/labels/1", None),
        ("delete", "/api/v1/tasks/1/labels/1", None),
        ("post", "/api/v1/tasks/1/comments", {"content": "Hi"}),
        ("get", "/api/v1/tasks/1/comments", None),
        ("delete", "/api/v1/comments/1", None),
    ):
        res = client.request(
            method, path, **({"json": payload} if payload is not None else {})
        )
        assert res.status_code == 401
        assert res.json() == {"detail": NOT_AUTHENTICATED}
        assert res.headers.get("WWW-Authenticate") == "Bearer"


def test_label_crud_and_validation(
    client: TestClient, setup_data: dict[str, int]
) -> None:
    # Missing project -> 404
    res_404 = client.post(
        "/api/v1/projects/999/labels",
        headers=auth_headers(1),
        json={"name": "Bug"},
    )
    assert res_404.status_code == 404
    assert res_404.json() == {"detail": PROJECT_NOT_FOUND}

    # Validation errors -> 422
    for bad_payload in (
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"name": "Bug", "color": "red"},
        {"name": "Bug", "color": "#12345"},
        {"name": "Bug", "color": "#GGGGGG"},
        {"name": "Bug", "project_id": 1},
    ):
        assert (
            client.post(
                "/api/v1/projects/1/labels",
                headers=auth_headers(1),
                json=bad_payload,
            ).status_code
            == 422
        )

    # Create with default color
    l1_res = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(4),
        json={"name": "  Bug  "},
    )
    assert l1_res.status_code == 201, l1_res.text
    l1 = l1_res.json()
    assert l1["name"] == "Bug"
    assert l1["color"] == DEFAULT_LABEL_COLOR
    assert l1["project_id"] == 1

    # Duplicate label name in same project (case-insensitive) -> 409
    dup_res = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(1),
        json={"name": "bug", "color": "#FF0000"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json() == {"detail": LABEL_ALREADY_EXISTS}

    # Same label name allowed in project 2 -> 201
    l_p2_res = client.post(
        "/api/v1/projects/2/labels",
        headers=auth_headers(1),
        json={"name": "Bug", "color": "#FF0000"},
    )
    assert l_p2_res.status_code == 201

    # Create second label in project 1
    l2 = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(1),
        json={"name": "Feature", "color": "#00FF00"},
    ).json()

    # List project 1 labels (viewer allowed)
    list_res = client.get("/api/v1/projects/1/labels", headers=auth_headers(6))
    assert list_res.status_code == 200
    assert [label["name"] for label in list_res.json()] == ["Bug", "Feature"]

    # Update validation: reject explicit null, duplicate name
    assert (
        client.patch(
            f"/api/v1/labels/{l2['id']}",
            headers=auth_headers(1),
            json={"name": None},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/labels/{l2['id']}",
            headers=auth_headers(1),
            json={"color": None},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/labels/{l2['id']}",
            headers=auth_headers(1),
            json={"name": "BUG"},
        ).status_code
        == 409
    )

    # Empty patch preserves data
    assert (
        client.patch(
            f"/api/v1/labels/{l2['id']}", headers=auth_headers(1), json={}
        ).json()
        == l2
    )

    # Update label color and name
    upd_res = client.patch(
        f"/api/v1/labels/{l2['id']}",
        headers=auth_headers(4),
        json={"name": "Enhancement", "color": "#1234AB"},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Enhancement"
    assert upd_res.json()["color"] == "#1234AB"

    # Delete label
    del_res = client.delete(f"/api/v1/labels/{l2['id']}", headers=auth_headers(4))
    assert del_res.status_code == 204
    assert del_res.content == b""
    assert (
        client.patch(
            f"/api/v1/labels/{l2['id']}",
            headers=auth_headers(1),
            json={"name": "Gone"},
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/labels/{l2['id']}", headers=auth_headers(1)).status_code
        == 404
    )


def test_label_rbac_and_archived_project(
    client: TestClient, setup_data: dict[str, int]
) -> None:
    label = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(1),
        json={"name": "Security"},
    ).json()

    # Non-member (user 2) gets 403
    res_create_non = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(2),
        json={"name": "Hacked"},
    )
    assert res_create_non.status_code == 403
    assert res_create_non.json() == {"detail": PROJECT_FORBIDDEN}
    assert (
        client.get("/api/v1/projects/1/labels", headers=auth_headers(2)).status_code
        == 403
    )
    res_patch_non = client.patch(
        f"/api/v1/labels/{label['id']}",
        headers=auth_headers(2),
        json={"name": "Hacked"},
    )
    assert res_patch_non.status_code == 403
    assert res_patch_non.json() == {"detail": LABEL_FORBIDDEN}
    assert (
        client.delete(
            f"/api/v1/labels/{label['id']}", headers=auth_headers(2)
        ).status_code
        == 403
    )

    # Viewer (user 6) can read, cannot write
    assert (
        client.get("/api/v1/projects/1/labels", headers=auth_headers(6)).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/projects/1/labels",
            headers=auth_headers(6),
            json={"name": "Viewer"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/labels/{label['id']}",
            headers=auth_headers(6),
            json={"name": "Viewer"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/labels/{label['id']}", headers=auth_headers(6)
        ).status_code
        == 403
    )

    # Archive project 1
    assert (
        client.patch(
            "/api/v1/projects/1",
            headers=auth_headers(1),
            json={"status": ProjectStatus.ARCHIVED.value},
        ).status_code
        == 200
    )

    # Reading still works; write ops return 400 PROJECT_ARCHIVED
    assert (
        client.get("/api/v1/projects/1/labels", headers=auth_headers(6)).status_code
        == 200
    )
    res_arch_create = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(1),
        json={"name": "New"},
    )
    assert res_arch_create.status_code == 400
    assert res_arch_create.json() == {"detail": PROJECT_ARCHIVED}
    assert (
        client.patch(
            f"/api/v1/labels/{label['id']}",
            headers=auth_headers(1),
            json={"name": "New"},
        ).status_code
        == 400
    )
    assert (
        client.delete(
            f"/api/v1/labels/{label['id']}", headers=auth_headers(1)
        ).status_code
        == 400
    )


def test_attach_detach_task_labels_and_cross_project_guard(
    client: TestClient, setup_data: dict[str, int]
) -> None:
    task1_id = setup_data["task1_id"]
    l_p1 = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(1),
        json={"name": "Backend", "color": "#112233"},
    ).json()
    l_p2 = client.post(
        "/api/v1/projects/2/labels",
        headers=auth_headers(1),
        json={"name": "Frontend", "color": "#445566"},
    ).json()

    # Cross-project guard: attaching project 2 label to project 1 task -> 400!
    cross_res = client.post(
        f"/api/v1/tasks/{task1_id}/labels/{l_p2['id']}",
        headers=auth_headers(1),
    )
    assert cross_res.status_code == 400
    assert cross_res.json() == {"detail": LABEL_DIFFERENT_PROJECT}

    # Missing task or label -> 404
    assert (
        client.post(
            f"/api/v1/tasks/999/labels/{l_p1['id']}", headers=auth_headers(1)
        ).status_code
        == 404
    )
    res_missing_lbl = client.post(
        f"/api/v1/tasks/{task1_id}/labels/999", headers=auth_headers(1)
    )
    assert res_missing_lbl.status_code == 404
    assert res_missing_lbl.json() == {"detail": LABEL_NOT_FOUND}

    # Non-member & Viewer blocked from attaching -> 403
    assert (
        client.post(
            f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
            headers=auth_headers(2),
        ).status_code
        == 403
    )
    res_viewer = client.post(
        f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
        headers=auth_headers(6),
    )
    assert res_viewer.status_code == 403
    assert res_viewer.json() == {"detail": TASK_FORBIDDEN}

    # Editor attaches same-project label -> 201
    attach_res = client.post(
        f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
        headers=auth_headers(4),
    )
    assert attach_res.status_code == 201, attach_res.text
    assert attach_res.json() == {
        "task_id": task1_id,
        "label_id": l_p1["id"],
        "name": "Backend",
        "color": "#112233",
    }

    # Duplicate attach -> 409
    dup_res = client.post(
        f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
        headers=auth_headers(4),
    )
    assert dup_res.status_code == 409
    assert dup_res.json() == {"detail": LABEL_ALREADY_ATTACHED}

    # Viewer & Editor can list task labels; non-member gets 403
    assert (
        client.get(
            f"/api/v1/tasks/{task1_id}/labels", headers=auth_headers(2)
        ).status_code
        == 403
    )
    list_res = client.get(f"/api/v1/tasks/{task1_id}/labels", headers=auth_headers(6))
    assert list_res.status_code == 200
    assert list_res.json() == [l_p1]

    # Viewer blocked from detaching -> 403
    assert (
        client.delete(
            f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
            headers=auth_headers(6),
        ).status_code
        == 403
    )

    # Editor detaches label -> 204
    del_res = client.delete(
        f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
        headers=auth_headers(4),
    )
    assert del_res.status_code == 204
    assert del_res.content == b""
    assert (
        client.get(f"/api/v1/tasks/{task1_id}/labels", headers=auth_headers(1)).json()
        == []
    )

    # Detaching again -> 404 TASK_LABEL_NOT_FOUND
    del_again = client.delete(
        f"/api/v1/tasks/{task1_id}/labels/{l_p1['id']}",
        headers=auth_headers(1),
    )
    assert del_again.status_code == 404
    assert del_again.json() == {"detail": TASK_LABEL_NOT_FOUND}


def test_comment_crud_rbac_and_ownership(
    client: TestClient, setup_data: dict[str, int]
) -> None:
    task1_id = setup_data["task1_id"]

    # Missing task -> 404
    res_404 = client.post(
        "/api/v1/tasks/999/comments",
        headers=auth_headers(1),
        json={"content": "Hello"},
    )
    assert res_404.status_code == 404
    assert res_404.json() == {"detail": TASK_NOT_FOUND}
    assert (
        client.get("/api/v1/tasks/999/comments", headers=auth_headers(1)).status_code
        == 404
    )

    # Validation errors -> 422
    for bad_payload in (
        {},
        {"content": ""},
        {"content": "   "},
        {"content": "x" * 5001},
        {"content": "Hello", "author_id": 1},
    ):
        assert (
            client.post(
                f"/api/v1/tasks/{task1_id}/comments",
                headers=auth_headers(1),
                json=bad_payload,
            ).status_code
            == 422
        )

    # Non-member (user 2) & Viewer (user 6) cannot create comments -> 403
    res_non = client.post(
        f"/api/v1/tasks/{task1_id}/comments",
        headers=auth_headers(2),
        json={"content": "Outsider"},
    )
    assert res_non.status_code == 403
    assert res_non.json() == {"detail": COMMENT_FORBIDDEN}

    res_viewer = client.post(
        f"/api/v1/tasks/{task1_id}/comments",
        headers=auth_headers(6),
        json={"content": "Viewer"},
    )
    assert res_viewer.status_code == 403
    assert res_viewer.json() == {"detail": COMMENT_FORBIDDEN}

    # Editor 1 (user 4) and Editor 2 (user 5) create comments
    c1_res = client.post(
        f"/api/v1/tasks/{task1_id}/comments",
        headers=auth_headers(4),
        json={"content": "  First comment  "},
    )
    assert c1_res.status_code == 201, c1_res.text
    c1 = c1_res.json()
    assert c1["task_id"] == task1_id
    assert c1["author_id"] == 4
    assert c1["content"] == "First comment"
    assert c1["created_at"].endswith("Z")

    c2 = client.post(
        f"/api/v1/tasks/{task1_id}/comments",
        headers=auth_headers(5),
        json={"content": "Second comment"},
    ).json()

    # Non-member cannot list comments -> 403; Viewer can list -> 200
    assert (
        client.get(
            f"/api/v1/tasks/{task1_id}/comments", headers=auth_headers(2)
        ).status_code
        == 403
    )
    list_res = client.get(f"/api/v1/tasks/{task1_id}/comments", headers=auth_headers(6))
    assert list_res.status_code == 200
    assert [c["id"] for c in list_res.json()] == [c1["id"], c2["id"]]

    # Ownership on DELETE:
    # - Editor 2 cannot delete Editor 1's comment -> 403
    del_other = client.delete(f"/api/v1/comments/{c1['id']}", headers=auth_headers(5))
    assert del_other.status_code == 403
    assert del_other.json() == {"detail": COMMENT_FORBIDDEN}

    # - Viewer cannot delete -> 403
    assert (
        client.delete(
            f"/api/v1/comments/{c1['id']}", headers=auth_headers(6)
        ).status_code
        == 403
    )

    # - Non-member cannot delete -> 403
    assert (
        client.delete(
            f"/api/v1/comments/{c1['id']}", headers=auth_headers(2)
        ).status_code
        == 403
    )

    # - Editor 1 can delete own comment -> 204
    assert (
        client.delete(
            f"/api/v1/comments/{c1['id']}", headers=auth_headers(4)
        ).status_code
        == 204
    )

    # - Workspace Owner (user 1) can delete Editor 2's comment -> 204
    assert (
        client.delete(
            f"/api/v1/comments/{c2['id']}", headers=auth_headers(1)
        ).status_code
        == 204
    )

    # - Platform ADMIN (user 3) can create & delete comment in any workspace
    c3 = client.post(
        f"/api/v1/tasks/{task1_id}/comments",
        headers=auth_headers(4),
        json={"content": "Admin will delete"},
    ).json()
    assert (
        client.delete(
            f"/api/v1/comments/{c3['id']}", headers=auth_headers(3)
        ).status_code
        == 204
    )

    # Missing comment -> 404
    del_404 = client.delete("/api/v1/comments/999", headers=auth_headers(1))
    assert del_404.status_code == 404
    assert del_404.json() == {"detail": COMMENT_NOT_FOUND}

    # Archived project blocks creating & deleting comments (reading still allowed)
    c4 = client.post(
        f"/api/v1/tasks/{task1_id}/comments",
        headers=auth_headers(4),
        json={"content": "Before archive"},
    ).json()
    assert (
        client.patch(
            "/api/v1/projects/1",
            headers=auth_headers(1),
            json={"status": ProjectStatus.ARCHIVED.value},
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/tasks/{task1_id}/comments", headers=auth_headers(6)
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/tasks/{task1_id}/comments",
            headers=auth_headers(4),
            json={"content": "Blocked"},
        ).status_code
        == 400
    )
    assert (
        client.delete(
            f"/api/v1/comments/{c4['id']}", headers=auth_headers(4)
        ).status_code
        == 400
    )
