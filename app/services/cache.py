import logging
from urllib.parse import quote

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.constants import DEFAULT_TASK_CACHE_TTL_SECONDS
from app.schemas.task import ProjectTaskQuery, TaskPage

logger = logging.getLogger(__name__)


def create_redis_client(redis_url: str) -> Redis:
    return aioredis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


class TaskCacheService:
    def __init__(
        self,
        redis_client: Redis | None = None,
        ttl_seconds: int = DEFAULT_TASK_CACHE_TTL_SECONDS,
    ) -> None:
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def build_project_tasks_key(project_id: int, query: ProjectTaskQuery) -> str:
        status_val = query.status.value if query.status is not None else "all"
        priority_val = query.priority.value if query.priority is not None else "all"
        assignee_val = (
            str(query.assignee_id) if query.assignee_id is not None else "all"
        )
        q_val = quote(query.q, safe="") if query.q is not None else ""
        return (
            f"tasks:project:{project_id}"
            f":status={status_val}"
            f":priority={priority_val}"
            f":assignee={assignee_val}"
            f":q={q_val}"
            f":page={query.page}"
            f":limit={query.limit}"
        )

    async def get_project_tasks(
        self, project_id: int, query: ProjectTaskQuery
    ) -> TaskPage | None:
        if self.redis_client is None:
            return None
        key = self.build_project_tasks_key(project_id, query)
        try:
            cached = await self.redis_client.get(key)
            if cached is None:
                return None
            return TaskPage.model_validate_json(cached)
        except (RedisError, OSError, ValueError) as exc:
            logger.warning("Redis cache get failed for key %s: %s", key, exc)
            return None

    async def set_project_tasks(
        self, project_id: int, query: ProjectTaskQuery, page: TaskPage
    ) -> None:
        if self.redis_client is None:
            return
        key = self.build_project_tasks_key(project_id, query)
        try:
            await self.redis_client.set(
                key, page.model_dump_json(), ex=self.ttl_seconds
            )
        except (RedisError, OSError) as exc:
            logger.warning("Redis cache set failed for key %s: %s", key, exc)

    async def invalidate_project_tasks(self, project_id: int) -> None:
        if self.redis_client is None:
            return
        pattern = f"tasks:project:{project_id}:*"
        try:
            keys: list[str] = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis_client.delete(*keys)
        except (RedisError, OSError) as exc:
            logger.warning(
                "Redis cache invalidation failed for project %s: %s",
                project_id,
                exc,
            )
