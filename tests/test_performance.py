import asyncio
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.constants import PROCESS_TIME_HEADER, REQUEST_ID_HEADER
from app.db.session import create_database_engine
from app.main import app
from app.models import Comment, Task, Workspace
from app.models.enums import TaskStatus, WorkspaceRole
from app.repositories.comment import CommentRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.comment import CommentQuery
from app.schemas.task import TaskQuery


def test_pagination_skips_count_query_on_partial_pages(database_url: str) -> None:
    async def check() -> None:
        engine = create_database_engine(database_url)
        executed_sql: list[str] = []

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def record_sql(
            _conn: Any,
            _cursor: Any,
            statement: str,
            _params: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            executed_sql.append(statement)

        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                session.add_all(
                    [
                        Task(project_id=1, title=f"Task {i}", created_by=1)
                        for i in range(1, 4)
                    ]
                )
                await session.flush()

                task_repo = TaskRepository(session)
                comment_repo = CommentRepository(session)
                workspace_repo = WorkspaceRepository(session)

                # Page 1 with limit 10 has 3 items (< limit) -> 1 SELECT, no COUNT(*)
                executed_sql.clear()
                items, total = await task_repo.search(
                    TaskQuery(page=1, limit=10), user_id=1
                )
                assert len(items) == 3
                assert total == 3
                assert len(executed_sql) == 1
                assert "count(" not in executed_sql[0].lower()

                # Page 2 with limit 2 returns 1 item (< limit) -> skips COUNT(*)
                executed_sql.clear()
                items_p2, total_p2 = await task_repo.search(
                    TaskQuery(page=2, limit=2), user_id=1
                )
                assert len(items_p2) == 1
                assert total_p2 == 3
                assert len(executed_sql) == 1

                # Page 1 with limit 2 returns full page (2 == limit) -> runs COUNT(*)
                executed_sql.clear()
                items_full, total_full = await task_repo.search(
                    TaskQuery(page=1, limit=2), user_id=1
                )
                assert len(items_full) == 2
                assert total_full == 3
                assert len(executed_sql) == 2

                # Empty page > 1 must still query COUNT(*) to report real total
                executed_sql.clear()
                items_empty, total_empty = await task_repo.search(
                    TaskQuery(page=4, limit=2), user_id=1
                )
                assert items_empty == []
                assert total_empty == 3
                assert len(executed_sql) == 2

                # CommentRepository and WorkspaceRepository also skip COUNT(*)
                task_id = items[0].id
                session.add(Comment(task_id=task_id, author_id=1, content="Ping"))
                await session.flush()

                executed_sql.clear()
                comments, c_total = await comment_repo.list_by_task(
                    task_id, CommentQuery(page=1, limit=10)
                )
                assert len(comments) == 1
                assert c_total == 1
                assert len(executed_sql) == 1

                executed_sql.clear()
                workspaces, w_total = await workspace_repo.search_for_user(
                    user_id=1, page=1, limit=10
                )
                assert len(workspaces) == 1
                assert w_total == 1
                assert len(executed_sql) == 1
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_get_effective_role_executes_single_query(database_url: str) -> None:
    async def check() -> None:
        engine = create_database_engine(database_url)
        executed_sql: list[str] = []

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def record_sql(
            _conn: Any,
            _cursor: Any,
            statement: str,
            _params: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            executed_sql.append(statement)

        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                owner_only_ws = Workspace(name="Direct Owner", owner_id=1)
                session.add(owner_only_ws)
                await session.flush()

                repo = WorkspaceRepository(session)

                for uid, ws_id, expected in (
                    (1, 1, WorkspaceRole.OWNER),
                    (1, owner_only_ws.id, WorkspaceRole.OWNER),
                    (2, 1, None),
                    (1, 99999, None),
                ):
                    executed_sql.clear()
                    role = await repo.get_effective_role(ws_id, uid)
                    assert role == expected
                    assert len(executed_sql) == 1

                executed_sql.clear()
                assert await repo.user_exists(1) is True
                assert len(executed_sql) == 1
                assert await repo.user_exists(99999) is False
        finally:
            await engine.dispose()

    asyncio.run(check())


def test_end_to_end_full_api_workflow(database_url: str) -> None:
    with TestClient(app) as client:
        # 1. Health & OpenAPI check
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert REQUEST_ID_HEADER in health.headers
        assert float(health.headers[PROCESS_TIME_HEADER]) >= 0.0
        assert client.get("/openapi.json").status_code == 200

        # 2. Register & login new workspace owner + editor
        for idx in (1, 2):
            reg = client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"e2e-u{idx}@example.com",
                    "full_name": f"E2E User {idx}",
                    "password": "StrongPassword123!",
                },
            )
            assert reg.status_code == 201

        login_1 = client.post(
            "/api/v1/auth/login",
            json={"email": "e2e-u1@example.com", "password": "StrongPassword123!"},
        ).json()
        login_2 = client.post(
            "/api/v1/auth/login",
            json={"email": "e2e-u2@example.com", "password": "StrongPassword123!"},
        ).json()
        h1 = {"Authorization": f"Bearer {login_1['access_token']}"}
        h2 = {"Authorization": f"Bearer {login_2['access_token']}"}
        u2_id = client.get("/api/v1/users/me", headers=h2).json()["id"]

        # 3. Workspace + member + project + task + label + comment flow
        ws_id = client.post(
            "/api/v1/workspaces", headers=h1, json={"name": "E2E Workspace"}
        ).json()["id"]
        assert (
            client.post(
                f"/api/v1/workspaces/{ws_id}/members",
                headers=h1,
                json={"user_id": u2_id, "role": "EDITOR"},
            ).status_code
            == 201
        )
        proj_id = client.post(
            f"/api/v1/workspaces/{ws_id}/projects",
            headers=h1,
            json={"name": "E2E Project"},
        ).json()["id"]
        task = client.post(
            f"/api/v1/projects/{proj_id}/tasks",
            headers=h1,
            json={"title": "Ship v1", "assignee_id": u2_id},
        ).json()
        label = client.post(
            f"/api/v1/projects/{proj_id}/labels",
            headers=h1,
            json={"name": "Release", "color": "#22AA44"},
        ).json()
        assert (
            client.post(
                f"/api/v1/tasks/{task['id']}/labels/{label['id']}",
                headers=h2,
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/v1/tasks/{task['id']}/comments",
                headers=h2,
                json={"content": "Ready to verify"},
            ).status_code
            == 201
        )

        # 4. Update task, check paginated task/comment lists, refresh & logout
        upd = client.patch(
            f"/api/v1/tasks/{task['id']}",
            headers=h2,
            json={"status": TaskStatus.DONE.value},
        )
        assert upd.status_code == 200
        assert upd.json()["status"] == TaskStatus.DONE.value

        listed_tasks = client.get(
            f"/api/v1/projects/{proj_id}/tasks", headers=h1
        ).json()
        assert listed_tasks["total"] == 1
        assert listed_tasks["items"][0]["status"] == TaskStatus.DONE.value

        listed_comments = client.get(
            f"/api/v1/tasks/{task['id']}/comments", headers=h1
        ).json()
        assert listed_comments["total"] == 1

        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_1["refresh_token"]},
        )
        assert refreshed.status_code == 200
        logout = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refreshed.json()["refresh_token"]},
        )
        assert logout.status_code == 204
