from app.core.constants import (
    ASSIGNEE_NOT_FOUND,
    ASSIGNEE_NOT_WORKSPACE_MEMBER,
)
from app.core.exceptions import BadRequestException, NotFoundException
from app.models import Task, User
from app.models.enums import UserRole
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.task import (
    ProjectTaskQuery,
    TaskFields,
    TaskPage,
    TaskQuery,
    TaskRead,
    TaskUpdate,
)
from app.services.permissions import load_project_for_user, load_task_for_user


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        project_repository: ProjectRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.workspace_repository = workspace_repository

    async def get(self, task_id: int, user: User) -> Task:
        task, _, _ = await load_task_for_user(
            self.repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=False,
        )
        return task

    async def create(self, project_id: int, payload: TaskFields, user: User) -> Task:
        project, _ = await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            project_id,
            user,
            write=True,
        )
        await self.check_assignee(payload.assignee_id, project.workspace_id)
        data = payload.model_dump(exclude={"project_id"})
        return await self.repository.create(
            Task(**data, project_id=project_id, created_by=user.id)
        )

    async def list(self, query: TaskQuery, user: User) -> TaskPage:
        tasks, total = await self.repository.search(
            query,
            user_id=user.id,
            is_admin=user.role == UserRole.ADMIN,
        )
        return TaskPage(
            items=[TaskRead.model_validate(task) for task in tasks],
            total=total,
            page=query.page,
            limit=query.limit,
        )

    async def list_by_project(
        self, project_id: int, query: ProjectTaskQuery, user: User
    ) -> TaskPage:
        await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            project_id,
            user,
            write=False,
        )
        task_query = TaskQuery(**query.model_dump(), project_id=project_id)
        return await self.list(task_query, user)

    async def update(self, task_id: int, payload: TaskUpdate, user: User) -> Task:
        task, project, _ = await load_task_for_user(
            self.repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
        )
        values = payload.model_dump(exclude_unset=True)
        if "assignee_id" in values:
            await self.check_assignee(payload.assignee_id, project.workspace_id)
        if not values:
            return task
        return await self.repository.update(task, values)

    async def delete(self, task_id: int, user: User) -> None:
        task, _, _ = await load_task_for_user(
            self.repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
        )
        await self.repository.delete(task)

    async def check_assignee(self, assignee_id: int | None, workspace_id: int) -> None:
        if assignee_id is None:
            return
        if not await self.repository.user_exists(assignee_id):
            raise NotFoundException(ASSIGNEE_NOT_FOUND)
        role = await self.workspace_repository.get_effective_role(
            workspace_id, assignee_id
        )
        if role is None:
            raise BadRequestException(ASSIGNEE_NOT_WORKSPACE_MEMBER)
