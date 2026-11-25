import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.security import create_access_token
from app.db.session import create_database_engine
from app.main import app
from app.models import Workspace
from tests.conftest import TEST_JWT_SECRET


def _auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(subject=user_id, secret_key=TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


def test_owner_without_member_row_has_consistent_workspace_and_project_rbac(
    database_url: str,
) -> None:
    async def seed_owner_only_workspace() -> int:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                ws = Workspace(name="Owner Only WS", owner_id=1)
                session.add(ws)
                await session.flush()
                return ws.id
        finally:
            await engine.dispose()

    ws_id = asyncio.run(seed_owner_only_workspace())

    with TestClient(app) as client:
        owner_headers = _auth_headers(1)
        outsider_headers = _auth_headers(2)

        assert (
            client.get(f"/api/v1/workspaces/{ws_id}", headers=owner_headers).status_code
            == 200
        )
        assert (
            client.patch(
                f"/api/v1/workspaces/{ws_id}",
                headers=owner_headers,
                json={"name": "Owner Only Updated"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/workspaces/{ws_id}/projects",
                headers=owner_headers,
                json={"name": "Owner Project"},
            ).status_code
            == 201
        )
        assert (
            client.get(
                f"/api/v1/workspaces/{ws_id}", headers=outsider_headers
            ).status_code
            == 403
        )


def test_utc_timestamps_consistent_across_resources(database_url: str) -> None:
    with TestClient(app) as client:
        reg_res = client.post(
            "/api/v1/auth/register",
            json={
                "email": "utc-check@example.com",
                "full_name": "UTC Check",
                "password": "StrongPassword123!",
            },
        )
        assert reg_res.status_code == 201
        assert reg_res.json()["created_at"].endswith("Z")

        headers = _auth_headers(1)
        ws_res = client.post(
            "/api/v1/workspaces", headers=headers, json={"name": "UTC WS"}
        )
        assert ws_res.status_code == 201
        assert ws_res.json()["created_at"].endswith("Z")
        ws_id = ws_res.json()["id"]

        proj_res = client.post(
            f"/api/v1/workspaces/{ws_id}/projects",
            headers=headers,
            json={"name": "UTC Project"},
        )
        assert proj_res.status_code == 201
        assert proj_res.json()["created_at"].endswith("Z")
        proj_id = proj_res.json()["id"]

        task_res = client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            headers=headers,
            json={"title": "UTC Task"},
        )
        assert task_res.status_code == 201
        assert task_res.json()["created_at"].endswith("Z")


def test_workspace_wildcard_search_uses_literal_matching(database_url: str) -> None:
    with TestClient(app, headers=_auth_headers(1)) as client:
        for name in ("100% Done", "alpha_beta", "alphaXbeta"):
            res = client.post("/api/v1/workspaces", json={"name": name})
            assert res.status_code == 201

        pct = client.get("/api/v1/workspaces", params={"q": "%"}).json()
        assert [w["name"] for w in pct["items"]] == ["100% Done"]

        underscore = client.get("/api/v1/workspaces", params={"q": "_"}).json()
        assert [w["name"] for w in underscore["items"]] == ["alpha_beta"]


def test_explicit_null_rejected_uniformly_across_patch_schemas(
    database_url: str,
) -> None:
    with TestClient(app, headers=_auth_headers(1)) as client:
        task_id = client.post(
            "/api/v1/projects/1/tasks", json={"title": "Null Guard"}
        ).json()["id"]
        label_id = client.post(
            "/api/v1/projects/1/labels", json={"name": "Guard"}
        ).json()["id"]

        cases = [
            ("/api/v1/users/me", {"full_name": None}),
            ("/api/v1/workspaces/1", {"name": None}),
            ("/api/v1/projects/1", {"name": None}),
            ("/api/v1/projects/1", {"status": None}),
            (f"/api/v1/tasks/{task_id}", {"title": None}),
            (f"/api/v1/tasks/{task_id}", {"status": None}),
            (f"/api/v1/tasks/{task_id}", {"priority": None}),
            (f"/api/v1/labels/{label_id}", {"name": None}),
            (f"/api/v1/labels/{label_id}", {"color": None}),
        ]
        for path, payload in cases:
            res = client.patch(path, json=payload)
            assert res.status_code == 422, f"Expected 422 for PATCH {path} {payload}"
