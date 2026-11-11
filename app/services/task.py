from app.core.constants import TASK_LIMIT_DEFAULT
from app.core.exceptions import NotFoundError
from app.core.messages import TASK_NOT_FOUND
from app.repositories.task import TaskRepository
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskPatch,
    TaskRead,
    TaskUpdate,
)


class TaskService:
    """Task service encapsulating business logic."""

    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def create(self, payload: TaskCreate) -> TaskRead:
        return self._repository.create(payload)

    def get(self, task_id: int) -> TaskRead:
        task = self._repository.get(task_id)
        if task is None:
            raise NotFoundError(TASK_NOT_FOUND)
        return task

    def list(
        self, q: str | None = None, limit: int = TASK_LIMIT_DEFAULT
    ) -> TaskListResponse:
        items, total = self._repository.list(q=q, limit=limit)
        return TaskListResponse(items=items, total=total)

    def update(self, task_id: int, payload: TaskUpdate) -> TaskRead:
        task = self._repository.update(task_id, payload)
        if task is None:
            raise NotFoundError(TASK_NOT_FOUND)
        return task

    def patch(self, task_id: int, payload: TaskPatch) -> TaskRead:
        task = self._repository.patch(task_id, payload)
        if task is None:
            raise NotFoundError(TASK_NOT_FOUND)
        return task

    def delete(self, task_id: int) -> None:
        deleted = self._repository.delete(task_id)
        if not deleted:
            raise NotFoundError(TASK_NOT_FOUND)
