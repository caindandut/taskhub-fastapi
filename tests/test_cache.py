import asyncio
import fnmatch
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.dependencies import get_redis_client
from app.core.security import create_access_token
from app.db.session import create_database_engine
from app.main import app
from app.models import Project
from app.models.enums import ProjectStatus, TaskPriority, TaskStatus
from app.repositories.task import TaskRepository
from app.schemas.task import ProjectTaskQuery
from app.services.cache import TaskCacheService
from tests.conftest import TEST_JWT_SECRET


def auth_headers(user_id: int = 1) -> dict[str, str]:
    token = create_access_token(subject=user_id, secret_key=TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


class FakeAsyncRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, int | None]] = []
        self.delete_calls: list[tuple[str, ...]] = []

    async def get(self, key: str) -> str | None:
        self.get_calls.append(key)
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls.append((key, ex))
        self.store[key] = value
        self.ttls[key] = ex
        return True

    async def scan_iter(self, match: str = "*") -> AsyncIterator[str]:
        for key in list(self.store.keys()):
            if fnmatch.fnmatchcase(key, match):
                yield key

    async def delete(self, *keys: str) -> int:
        self.delete_calls.append(keys)
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                self.ttls.pop(key, None)
                removed += 1
        return removed


@pytest.fixture
def fake_redis(database_url: str) -> Iterator[FakeAsyncRedis]:
    redis = FakeAsyncRedis()
    app.dependency_overrides[get_redis_client] = lambda: redis
    try:
        yield redis
    finally:
        app.dependency_overrides.pop(get_redis_client, None)


@pytest.fixture
def client(fake_redis: FakeAsyncRedis) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_cache_hit_miss_and_ttl(
    client: TestClient,
    fake_redis: FakeAsyncRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Cached Task"},
    )
    fake_redis.get_calls.clear()
    fake_redis.set_calls.clear()

    search_spy = AsyncMock(wraps=TaskRepository.search)

    async def wrapped_search(self: TaskRepository, **kwargs):
        return await search_spy(self, **kwargs)

    monkeypatch.setattr(TaskRepository, "search", wrapped_search)

    # First call -> cache MISS -> queries DB and writes cache
    r1 = client.get("/api/v1/projects/1/tasks", headers=auth_headers(1))
    assert r1.status_code == 200
    assert r1.json()["total"] == 1
    assert r1.json()["items"][0]["title"] == "Cached Task"
    assert search_spy.call_count == 1
    assert len(fake_redis.get_calls) == 1
    assert len(fake_redis.set_calls) == 1
    key, ttl = fake_redis.set_calls[0]
    assert key.startswith("tasks:project:1:")
    assert ttl == 300

    # Second call with same parameters -> cache HIT -> NO DB search query
    r2 = client.get("/api/v1/projects/1/tasks", headers=auth_headers(1))
    assert r2.status_code == 200
    assert r2.json() == r1.json()
    assert search_spy.call_count == 1
    assert len(fake_redis.get_calls) == 2
    assert len(fake_redis.set_calls) == 1


def test_cache_keys_distinguish_filters_and_pagination(
    client: TestClient, fake_redis: FakeAsyncRedis
) -> None:
    client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={
            "title": "Alpha bug* fix",
            "status": TaskStatus.TODO.value,
            "priority": TaskPriority.HIGH.value,
            "assignee_id": 1,
        },
    )
    client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={
            "title": "Beta feature",
            "status": TaskStatus.DONE.value,
            "priority": TaskPriority.LOW.value,
        },
    )
    fake_redis.store.clear()

    r_todo = client.get(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        params={"status": "TODO", "priority": "HIGH", "assignee_id": 1, "q": "bug*"},
    )
    assert r_todo.status_code == 200
    assert r_todo.json()["total"] == 1

    r_done = client.get(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        params={"status": "DONE", "page": 1, "limit": 5},
    )
    assert r_done.status_code == 200
    assert r_done.json()["total"] == 1
    assert r_done.json()["items"][0]["title"] == "Beta feature"

    assert len(fake_redis.store) == 2
    keys = list(fake_redis.store.keys())
    assert any("status=TODO:priority=HIGH:assignee=1:q=bug%2A" in k for k in keys)
    assert any(
        "status=DONE:priority=all:assignee=all:q=:page=1:limit=5" in k for k in keys
    )


def test_rbac_still_enforced_when_cached(
    client: TestClient, fake_redis: FakeAsyncRedis
) -> None:
    client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Private Task"},
    )
    # Warm cache as Owner (user 1)
    assert (
        client.get("/api/v1/projects/1/tasks", headers=auth_headers(1)).status_code
        == 200
    )
    assert len(fake_redis.store) == 1

    # Non-member (user 2) must still get 403 even though cache is populated
    res_forbidden = client.get("/api/v1/projects/1/tasks", headers=auth_headers(2))
    assert res_forbidden.status_code == 403


def test_cache_invalidation_on_task_label_and_project_mutations(
    client: TestClient, fake_redis: FakeAsyncRedis, database_url: str
) -> None:
    # Seed project 10 (to verify project 1 invalidation does NOT wipe project 10!)
    async def add_other_projects() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                session.add_all(
                    [
                        Project(id=2, workspace_id=1, name="Second"),
                        Project(id=10, workspace_id=1, name="Tenth"),
                    ]
                )
        finally:
            await engine.dispose()

    asyncio.run(add_other_projects())

    # Create initial task in project 1 and warm caches for projects 1, 2, 10
    task = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Task 1"},
    ).json()
    label = client.post(
        "/api/v1/projects/1/labels",
        headers=auth_headers(1),
        json={"name": "Urgent"},
    ).json()

    def warm_all() -> None:
        for pid in (1, 2, 10):
            assert (
                client.get(
                    f"/api/v1/projects/{pid}/tasks", headers=auth_headers(1)
                ).status_code
                == 200
            )
        assert any(k.startswith("tasks:project:1:") for k in fake_redis.store)
        assert any(k.startswith("tasks:project:2:") for k in fake_redis.store)
        assert any(k.startswith("tasks:project:10:") for k in fake_redis.store)

    # 1. Create task in project 1 invalidates project 1 only
    warm_all()
    t2 = client.post(
        "/api/v1/tasks",
        headers=auth_headers(1),
        json={"title": "Task 2", "project_id": 1},
    ).json()
    assert not any(k.startswith("tasks:project:1:") for k in fake_redis.store)
    assert any(k.startswith("tasks:project:2:") for k in fake_redis.store)
    assert any(k.startswith("tasks:project:10:") for k in fake_redis.store)

    # 2. Update task in project 1 invalidates project 1
    warm_all()
    assert (
        client.patch(
            f"/api/v1/tasks/{task['id']}",
            headers=auth_headers(1),
            json={"title": "Task 1 Edited"},
        ).status_code
        == 200
    )
    assert not any(k.startswith("tasks:project:1:") for k in fake_redis.store)
    assert any(k.startswith("tasks:project:10:") for k in fake_redis.store)
    refreshed = client.get("/api/v1/projects/1/tasks", headers=auth_headers(1)).json()
    assert refreshed["items"][0]["title"] == "Task 1 Edited"

    # 3. Attach & detach label on task invalidates project 1
    warm_all()
    assert (
        client.post(
            f"/api/v1/tasks/{task['id']}/labels/{label['id']}",
            headers=auth_headers(1),
        ).status_code
        == 201
    )
    assert not any(k.startswith("tasks:project:1:") for k in fake_redis.store)

    warm_all()
    assert (
        client.delete(
            f"/api/v1/tasks/{task['id']}/labels/{label['id']}",
            headers=auth_headers(1),
        ).status_code
        == 204
    )
    assert not any(k.startswith("tasks:project:1:") for k in fake_redis.store)

    # 4. Delete task invalidates project 1
    warm_all()
    assert (
        client.delete(f"/api/v1/tasks/{t2['id']}", headers=auth_headers(1)).status_code
        == 204
    )
    assert not any(k.startswith("tasks:project:1:") for k in fake_redis.store)

    # 5. Archive project 1 invalidates project 1
    warm_all()
    assert (
        client.patch(
            "/api/v1/projects/1",
            headers=auth_headers(1),
            json={"status": ProjectStatus.ARCHIVED.value},
        ).status_code
        == 200
    )
    assert not any(k.startswith("tasks:project:1:") for k in fake_redis.store)

    # 6. Delete project 2 invalidates project 2 without touching project 10
    warm_all()
    assert (
        client.delete("/api/v1/projects/2", headers=auth_headers(1)).status_code == 204
    )
    assert not any(k.startswith("tasks:project:2:") for k in fake_redis.store)
    assert any(k.startswith("tasks:project:10:") for k in fake_redis.store)


def test_redis_unavailable_graceful_fallback(database_url: str) -> None:
    failing_redis = AsyncMock()
    failing_redis.get.side_effect = RedisConnectionError("Redis connection refused")
    failing_redis.set.side_effect = RedisConnectionError("Redis connection refused")
    failing_redis.delete.side_effect = RedisConnectionError("Redis connection refused")

    async def failing_scan_iter(**kwargs):
        raise RedisConnectionError("Redis connection refused")
        yield  # pragma: no cover

    failing_redis.scan_iter = failing_scan_iter
    app.dependency_overrides[get_redis_client] = lambda: failing_redis
    try:
        with TestClient(app, headers=auth_headers(1)) as client:
            # Create task still succeeds even if invalidation fails
            create_res = client.post(
                "/api/v1/projects/1/tasks",
                json={"title": "Fallback Task"},
            )
            assert create_res.status_code == 201
            task_id = create_res.json()["id"]

            # List tasks falls back to DB cleanly
            list_res = client.get("/api/v1/projects/1/tasks")
            assert list_res.status_code == 200
            assert list_res.json()["total"] == 1
            assert list_res.json()["items"][0]["id"] == task_id

            # Update and delete also succeed cleanly
            assert (
                client.patch(
                    f"/api/v1/tasks/{task_id}", json={"title": "Updated Fallback"}
                ).status_code
                == 200
            )
            assert client.delete(f"/api/v1/tasks/{task_id}").status_code == 204
    finally:
        app.dependency_overrides.pop(get_redis_client, None)


def test_corrupt_cached_json_falls_back_and_repairs_cache(
    client: TestClient, fake_redis: FakeAsyncRedis
) -> None:
    client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Healthy Task"},
    )
    key = TaskCacheService.build_project_tasks_key(1, ProjectTaskQuery())
    fake_redis.store[key] = "{not-valid-json"

    res = client.get("/api/v1/projects/1/tasks", headers=auth_headers(1))
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["title"] == "Healthy Task"
    assert fake_redis.store[key] != "{not-valid-json"


def test_redis_settings_validation_and_lifespan(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Blank string normalizes to None
    s_blank = Settings(
        database_url=database_url,
        jwt_secret_key=TEST_JWT_SECRET,
        redis_url="   ",
    )
    assert s_blank.redis_url is None

    # Valid redis:// and rediss://
    s_ok = Settings(
        database_url=database_url,
        jwt_secret_key=TEST_JWT_SECRET,
        redis_url="  redis://localhost:6379/1  ",
    )
    assert s_ok.redis_url == "redis://localhost:6379/1"

    # Invalid URLs rejected
    for bad_url in ("http://localhost:6379/0", "redis:///0"):
        with pytest.raises(ValidationError):
            Settings(
                database_url=database_url,
                jwt_secret_key=TEST_JWT_SECRET,
                redis_url=bad_url,
            )

    # App lifespan initializes and closes redis client cleanly even if server unreachable
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    get_settings.cache_clear()
    try:
        with TestClient(app, headers=auth_headers(1)) as client:
            assert app.state.redis_client is not None
            # Endpoint still succeeds via graceful fallback when port 6399 is closed
            res = client.get("/api/v1/projects/1/tasks")
            assert res.status_code == 200
            assert res.json()["total"] == 0
    finally:
        get_settings.cache_clear()
