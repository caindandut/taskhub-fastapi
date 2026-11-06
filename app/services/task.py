from app.core.constants import (
    ASSIGNEE_NOT_FOUND,
    CREATOR_NOT_FOUND,
    PROJECT_NOT_FOUND,
    TASK_NOT_FOUND,
)
from app.core.exceptions import NotFoundException
from app.models import Task
from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskPage, TaskQuery, TaskRead, TaskUpdate


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    async def get(self, task_id: int) -> Task:
        task = await self.repository.get(task_id)
        if task is None:
            raise NotFoundException(TASK_NOT_FOUND)
        return task

    async def create(self, payload: TaskCreate) -> Task:
        if not await self.repository.project_exists(payload.project_id):
            raise NotFoundException(PROJECT_NOT_FOUND)
        if not await self.repository.user_exists(payload.created_by):
            raise NotFoundException(CREATOR_NOT_FOUND)
        await self.check_assignee(payload.assignee_id)
        return await self.repository.create(Task(**payload.model_dump()))

    async def list(self, query: TaskQuery) -> TaskPage:
        tasks, total = await self.repository.search(**query.model_dump())
        return TaskPage(
            items=[TaskRead.model_validate(task) for task in tasks],
            total=total,
            page=query.page,
            limit=query.limit,
        )

    async def update(self, task_id: int, payload: TaskUpdate) -> Task:
        task = await self.get(task_id)
        values = payload.model_dump(exclude_unset=True)
        if "assignee_id" in values:
            await self.check_assignee(payload.assignee_id)
        return await self.repository.update(task, values)

    async def delete(self, task_id: int) -> None:
        task = await self.get(task_id)
        await self.repository.delete(task)

    async def check_assignee(self, assignee_id: int | None) -> None:
        if assignee_id is not None and not await self.repository.user_exists(
            assignee_id
        ):
            raise NotFoundException(ASSIGNEE_NOT_FOUND)
