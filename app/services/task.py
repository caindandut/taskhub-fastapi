from app.core.constants import (
    ASSIGNEE_NOT_FOUND,
    ASSIGNEE_NOT_WORKSPACE_MEMBER,
    CREATOR_NOT_FOUND,
    PROJECT_ARCHIVED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
    TASK_NOT_FOUND,
)
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.models import Project, Task, User
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.task import (
    ProjectTaskQuery,
    TaskCreate,
    TaskPage,
    TaskQuery,
    TaskRead,
    TaskUpdate,
)


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.repository = repository
        self.workspace_repository = workspace_repository

    async def _require_project(self, project_id: int) -> Project:
        project = await self.repository.get_project(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)
        return project

    async def _check_project_access(
        self,
        project: Project,
        user: User,
        *,
        write: bool = False,
        forbidden_message: str = PROJECT_FORBIDDEN,
    ) -> None:
        if user.role != UserRole.ADMIN:
            role = await self.workspace_repository.get_effective_role(
                project.workspace_id, user.id
            )
            if role is None or (write and role == WorkspaceRole.VIEWER):
                raise ForbiddenException(forbidden_message)
        if write and project.status == ProjectStatus.ARCHIVED:
            raise BadRequestException(PROJECT_ARCHIVED)

    async def get(self, task_id: int, user: User) -> Task:
        task = await self.repository.get(task_id)
        if task is None:
            raise NotFoundException(TASK_NOT_FOUND)
        if user.role != UserRole.ADMIN:
            project = await self._require_project(task.project_id)
            await self._check_project_access(
                project, user, write=False, forbidden_message=TASK_FORBIDDEN
            )
        return task

    async def create(self, payload: TaskCreate, user: User) -> Task:
        project = await self._require_project(payload.project_id)
        await self._check_project_access(project, user, write=True)
        if not await self.repository.user_exists(user.id):
            raise NotFoundException(CREATOR_NOT_FOUND)
        await self.check_assignee(payload.assignee_id, project.workspace_id)
        return await self.repository.create(
            Task(**payload.model_dump(), created_by=user.id)
        )

    async def list(self, query: TaskQuery, user: User) -> TaskPage:
        is_admin = user.role == UserRole.ADMIN
        tasks, total = await self.repository.search(
            user_id=user.id,
            is_admin=is_admin,
            **query.model_dump(),
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
        project = await self._require_project(project_id)
        await self._check_project_access(project, user, write=False)
        task_query = TaskQuery(**query.model_dump(), project_id=project_id)
        return await self.list(task_query, user)

    async def update(self, task_id: int, payload: TaskUpdate, user: User) -> Task:
        task = await self.repository.get(task_id)
        if task is None:
            raise NotFoundException(TASK_NOT_FOUND)
        project = await self._require_project(task.project_id)
        await self._check_project_access(
            project, user, write=True, forbidden_message=TASK_FORBIDDEN
        )
        values = payload.model_dump(exclude_unset=True)
        if "assignee_id" in values:
            await self.check_assignee(payload.assignee_id, project.workspace_id)
        if not values:
            return task
        return await self.repository.update(task, values)

    async def delete(self, task_id: int, user: User) -> None:
        task = await self.repository.get(task_id)
        if task is None:
            raise NotFoundException(TASK_NOT_FOUND)
        project = await self._require_project(task.project_id)
        await self._check_project_access(
            project, user, write=True, forbidden_message=TASK_FORBIDDEN
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
