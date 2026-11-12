from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.constants import (
    CANNOT_MODIFY_WORKSPACE_OWNER,
    CANNOT_REMOVE_WORKSPACE_OWNER,
    MEMBER_ALREADY_EXISTS,
    MEMBER_NOT_FOUND,
    USER_NOT_FOUND,
    WORKSPACE_FORBIDDEN,
)
from app.core.security import create_access_token
from app.main import app
from app.models.enums import UserRole, WorkspaceRole
from tests.conftest import TEST_JWT_SECRET


def auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=user_id, secret_key=TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_create_workspace(client: TestClient) -> None:
    # Unauthenticated
    assert (
        client.post("/api/v1/workspaces", json={"name": "My Workspace"}).status_code
        == 401
    )

    # Authenticated user 1
    res = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "  Engineering Team  "},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["name"] == "Engineering Team"
    assert data["owner_id"] == 1
    assert data["id"] > 0
    assert data["created_at"]

    # Verify user 1 is in members as OWNER
    members_res = client.get(
        f"/api/v1/workspaces/{data['id']}/members",
        headers=auth_headers(1),
    )
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) == 1
    assert members[0]["user_id"] == 1
    assert members[0]["role"] == WorkspaceRole.OWNER.value
    assert members[0]["email"] == "owner@example.com"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": None},
        {"name": "x" * 101},
        {"name": "Valid", "extra": "forbidden"},
    ],
)
def test_create_workspace_validation_errors(client: TestClient, payload: dict) -> None:
    res = client.post("/api/v1/workspaces", headers=auth_headers(1), json=payload)
    assert res.status_code == 422


def test_list_and_search_workspaces(client: TestClient) -> None:
    # User 1 creates two workspaces
    ws1 = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "Alpha Project"},
    ).json()
    ws2 = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "Beta Team"},
    ).json()

    # User 2 creates a workspace
    client.post(
        "/api/v1/workspaces",
        headers=auth_headers(2),
        json={"name": "User 2 Workspace"},
    )

    # User 1 lists workspaces (sees seeded TaskHub + Alpha + Beta, but not User 2's workspace)
    res = client.get("/api/v1/workspaces", headers=auth_headers(1))
    assert res.status_code == 200
    page = res.json()
    assert page["total"] == 3
    workspace_ids = [w["id"] for w in page["items"]]
    assert ws1["id"] in workspace_ids
    assert ws2["id"] in workspace_ids

    # Search by query
    search_res = client.get(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        params={"q": "ALPHA"},
    )
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["items"][0]["name"] == "Alpha Project"

    # User 2 lists workspaces (only sees User 2 Workspace)
    u2_res = client.get("/api/v1/workspaces", headers=auth_headers(2))
    assert u2_res.json()["total"] == 1
    assert u2_res.json()["items"][0]["name"] == "User 2 Workspace"


def test_get_workspace_access_control(client: TestClient) -> None:
    # Seeded workspace 1 is owned by user 1
    # User 1 (owner) gets 200
    res = client.get("/api/v1/workspaces/1", headers=auth_headers(1))
    assert res.status_code == 200
    assert res.json()["name"] == "TaskHub"

    # User 2 (not a member) gets 403
    res_u2 = client.get("/api/v1/workspaces/1", headers=auth_headers(2))
    assert res_u2.status_code == 403
    assert res_u2.json() == {"detail": WORKSPACE_FORBIDDEN}

    # Non-existent workspace gets 404
    assert (
        client.get("/api/v1/workspaces/999", headers=auth_headers(1)).status_code == 404
    )


def test_update_workspace(client: TestClient) -> None:
    # User 1 creates workspace
    ws = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "Original Name"},
    ).json()

    # User 2 (non-owner) gets 403
    assert (
        client.patch(
            f"/api/v1/workspaces/{ws['id']}",
            headers=auth_headers(2),
            json={"name": "Hacked Name"},
        ).status_code
        == 403
    )

    # Owner updates name
    patch_res = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        headers=auth_headers(1),
        json={"name": "  Renamed Workspace  "},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Renamed Workspace"

    # Reject null
    assert (
        client.patch(
            f"/api/v1/workspaces/{ws['id']}",
            headers=auth_headers(1),
            json={"name": None},
        ).status_code
        == 422
    )

    # Empty payload preserves existing
    empty_res = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        headers=auth_headers(1),
        json={},
    )
    assert empty_res.status_code == 200
    assert empty_res.json()["name"] == "Renamed Workspace"


def test_delete_workspace(client: TestClient) -> None:
    ws = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "To Be Deleted"},
    ).json()

    # Non-owner cannot delete
    assert (
        client.delete(
            f"/api/v1/workspaces/{ws['id']}",
            headers=auth_headers(2),
        ).status_code
        == 403
    )

    # Owner deletes
    del_res = client.delete(
        f"/api/v1/workspaces/{ws['id']}",
        headers=auth_headers(1),
    )
    assert del_res.status_code == 204
    assert del_res.content == b""

    # Now 404
    assert (
        client.get(
            f"/api/v1/workspaces/{ws['id']}", headers=auth_headers(1)
        ).status_code
        == 404
    )


def test_workspace_membership_workflow(client: TestClient) -> None:
    ws = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "Collaboration Workspace"},
    ).json()
    ws_id = ws["id"]

    # 1. User 2 is not yet a member
    assert (
        client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(2)).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/workspaces/{ws_id}/members", headers=auth_headers(2)
        ).status_code
        == 403
    )

    # 2. Non-owner (User 2) cannot add member
    assert (
        client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            headers=auth_headers(2),
            json={"user_id": 2, "role": "EDITOR"},
        ).status_code
        == 403
    )

    # 3. Owner adds User 2 as EDITOR
    add_res = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers=auth_headers(1),
        json={"user_id": 2, "role": "EDITOR"},
    )
    assert add_res.status_code == 201, add_res.text
    member_data = add_res.json()
    assert member_data["workspace_id"] == ws_id
    assert member_data["user_id"] == 2
    assert member_data["role"] == "EDITOR"
    assert member_data["email"] == "member@example.com"

    # 4. User 2 can now access workspace and view members
    assert (
        client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(2)).status_code
        == 200
    )
    members_res = client.get(
        f"/api/v1/workspaces/{ws_id}/members", headers=auth_headers(2)
    )
    assert members_res.status_code == 200
    assert len(members_res.json()) == 2

    # 5. Adding already existing member returns 409
    dup_res = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers=auth_headers(1),
        json={"user_id": 2, "role": "VIEWER"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json() == {"detail": MEMBER_ALREADY_EXISTS}

    # 6. Adding non-existent user returns 404
    missing_user = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        headers=auth_headers(1),
        json={"user_id": 9999, "role": "VIEWER"},
    )
    assert missing_user.status_code == 404
    assert missing_user.json() == {"detail": USER_NOT_FOUND}

    # 7. Non-owner (User 2 - EDITOR) cannot modify role
    assert (
        client.patch(
            f"/api/v1/workspaces/{ws_id}/members/1",
            headers=auth_headers(2),
            json={"role": "VIEWER"},
        ).status_code
        == 403
    )

    # 8. Owner changes User 2 role to VIEWER
    patch_role = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/2",
        headers=auth_headers(1),
        json={"role": "VIEWER"},
    )
    assert patch_role.status_code == 200
    assert patch_role.json()["role"] == "VIEWER"

    # 9. Cannot modify workspace owner's role
    demote_owner = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/1",
        headers=auth_headers(1),
        json={"role": "VIEWER"},
    )
    assert demote_owner.status_code == 400
    assert demote_owner.json() == {"detail": CANNOT_MODIFY_WORKSPACE_OWNER}

    # 10. Cannot remove workspace owner
    del_owner = client.delete(
        f"/api/v1/workspaces/{ws_id}/members/1",
        headers=auth_headers(1),
    )
    assert del_owner.status_code == 400
    assert del_owner.json() == {"detail": CANNOT_REMOVE_WORKSPACE_OWNER}

    # 11. User 2 can leave the workspace voluntarily
    leave_res = client.delete(
        f"/api/v1/workspaces/{ws_id}/members/2",
        headers=auth_headers(2),
    )
    assert leave_res.status_code == 204
    # User 2 no longer has access
    assert (
        client.get(f"/api/v1/workspaces/{ws_id}", headers=auth_headers(2)).status_code
        == 403
    )

    # 12. Removing non-existent member returns 404
    del_missing = client.delete(
        f"/api/v1/workspaces/{ws_id}/members/2",
        headers=auth_headers(1),
    )
    assert del_missing.status_code == 404
    assert del_missing.json() == {"detail": MEMBER_NOT_FOUND}


def test_admin_superuser_access(client: TestClient, database_url: str) -> None:
    # Create an admin user (id=3, role=ADMIN)
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import create_database_engine
    from app.models import User
    from tests.conftest import TEST_PASSWORD_HASH

    async def add_admin() -> int:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                admin = User(
                    email="admin@example.com",
                    full_name="Admin",
                    hashed_password=TEST_PASSWORD_HASH,
                    role=UserRole.ADMIN,
                )
                session.add(admin)
                await session.flush()
                return admin.id
        finally:
            await engine.dispose()

    admin_id = asyncio.run(add_admin())
    admin_headers = auth_headers(admin_id)

    # User 1 creates workspace
    ws = client.post(
        "/api/v1/workspaces",
        headers=auth_headers(1),
        json={"name": "Admin Test Workspace"},
    ).json()
    ws_id = ws["id"]

    # Admin is not a member, but can view, update, list members, add members, delete
    assert (
        client.get(f"/api/v1/workspaces/{ws_id}", headers=admin_headers).status_code
        == 200
    )

    admin_patch = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        headers=admin_headers,
        json={"name": "Admin Renamed Workspace"},
    )
    assert admin_patch.status_code == 200
    assert admin_patch.json()["name"] == "Admin Renamed Workspace"

    # Admin adds user 2 as EDITOR
    assert (
        client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            headers=admin_headers,
            json={"user_id": 2, "role": "EDITOR"},
        ).status_code
        == 201
    )

    # Admin lists workspaces (sees all)
    all_ws = client.get("/api/v1/workspaces", headers=admin_headers)
    assert all_ws.status_code == 200
    assert ws_id in [w["id"] for w in all_ws.json()["items"]]

    # Admin deletes workspace
    assert (
        client.delete(f"/api/v1/workspaces/{ws_id}", headers=admin_headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/workspaces/{ws_id}", headers=admin_headers).status_code
        == 404
    )
