from typing import Annotated

from fastapi import Depends, Request

from app.repositories.task import TaskRepository
from app.schemas.task import TaskRead
from app.services.task import TaskService


def get_task_repository(request: Request) -> TaskRepository:
    """Return this application's task repository."""
    return request.app.state.task_repository


def get_task_service(
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
) -> TaskService:
    """Return task service initialized with repository."""
    return TaskService(repository)


def get_task_store(request: Request) -> dict[int, TaskRead]:
    """Return the raw in-memory dictionary for backwards compatibility."""
    return request.app.state.task_repository._store
