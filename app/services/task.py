from fastapi import BackgroundTasks

from app.core.constants import (
    ASSIGNEE_NOT_FOUND,
    ASSIGNEE_NOT_WORKSPACE_MEMBER,
)
from app.core.exceptions import BadRequestException, NotFoundException
from app.models import Project, Task, User
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
from app.services.cache import TaskCacheService
from app.services.notification import NotificationService, TaskAssignmentNotification
from app.services.permissions import load_project_for_user, load_task_for_user


class TaskService:
    def __init__(
        self,
        repository: TaskRepository,
        project_repository: ProjectRepository,
        workspace_repository: WorkspaceRepository,
        cache_service: TaskCacheService | None = None,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.workspace_repository = workspace_repository
        self.cache_service = cache_service or TaskCacheService()
        self.notification_service = notification_service or NotificationService()

    def _schedule_assignment_notification(
        self,
        background_tasks: BackgroundTasks | None,
        *,
        task: Task,
        project: Project,
        assignee: User,
        assigned_by: User,
    ) -> None:
        if background_tasks is None:
            return
        notification = TaskAssignmentNotification(
            task_id=task.id,
            task_title=task.title,
            project_id=project.id,
            project_name=project.name,
            assignee_id=assignee.id,
            assignee_email=assignee.email,
            assignee_name=assignee.full_name,
            assigned_by_id=assigned_by.id,
            assigned_by_name=assigned_by.full_name,
        )
        background_tasks.add_task(
            self.notification_service.send_task_assigned_email,
            notification,
        )

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

    async def create(
        self,
        project_id: int,
        payload: TaskFields,
        user: User,
        background_tasks: BackgroundTasks | None = None,
    ) -> Task:
        project, _ = await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            project_id,
            user,
            write=True,
        )
        assignee = await self.check_assignee(payload.assignee_id, project.workspace_id)
        data = payload.model_dump(exclude={"project_id"})
        task = await self.repository.create(
            Task(**data, project_id=project_id, created_by=user.id)
        )
        await self.cache_service.schedule_project_invalidation(
            project_id, background_tasks
        )
        if assignee is not None:
            self._schedule_assignment_notification(
                background_tasks,
                task=task,
                project=project,
                assignee=assignee,
                assigned_by=user,
            )
        return task

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
        cached = await self.cache_service.get_project_tasks(project_id, query)
        if cached is not None:
            return cached
        task_query = TaskQuery(**query.model_dump(), project_id=project_id)
        page = await self.list(task_query, user)
        await self.cache_service.set_project_tasks(project_id, query, page)
        return page

    async def update(
        self,
        task_id: int,
        payload: TaskUpdate,
        user: User,
        background_tasks: BackgroundTasks | None = None,
    ) -> Task:
        task, project, _ = await load_task_for_user(
            self.repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
        )
        previous_assignee_id = task.assignee_id
        values = payload.model_dump(exclude_unset=True)
        assignee: User | None = None
        if "assignee_id" in values:
            assignee = await self.check_assignee(
                payload.assignee_id, project.workspace_id
            )
        if not values:
            return task
        updated = await self.repository.update(task, values)
        await self.cache_service.schedule_project_invalidation(
            task.project_id, background_tasks
        )
        if assignee is not None and updated.assignee_id != previous_assignee_id:
            self._schedule_assignment_notification(
                background_tasks,
                task=updated,
                project=project,
                assignee=assignee,
                assigned_by=user,
            )
        return updated

    async def delete(
        self,
        task_id: int,
        user: User,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        task, _, _ = await load_task_for_user(
            self.repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
        )
        project_id = task.project_id
        await self.repository.delete(task)
        await self.cache_service.schedule_project_invalidation(
            project_id, background_tasks
        )

    async def check_assignee(
        self, assignee_id: int | None, workspace_id: int
    ) -> User | None:
        if assignee_id is None:
            return None
        assignee = await self.repository.get_user(assignee_id)
        if assignee is None:
            raise NotFoundException(ASSIGNEE_NOT_FOUND)
        role = await self.workspace_repository.get_effective_role(
            workspace_id, assignee_id
        )
        if role is None:
            raise BadRequestException(ASSIGNEE_NOT_WORKSPACE_MEMBER)
        return assignee
