from app.core.constants import (
    LABEL_ALREADY_ATTACHED,
    LABEL_ALREADY_EXISTS,
    LABEL_DIFFERENT_PROJECT,
    LABEL_FORBIDDEN,
    LABEL_NOT_FOUND,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
    TASK_LABEL_NOT_FOUND,
    TASK_NOT_FOUND,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models import Label, Project, Task, User
from app.repositories.label import LabelRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.label import LabelCreate, LabelUpdate, TaskLabelRead
from app.services.cache import TaskCacheService
from app.services.permissions import require_project_access


class LabelService:
    def __init__(
        self,
        repository: LabelRepository,
        project_repository: ProjectRepository,
        task_repository: TaskRepository,
        workspace_repository: WorkspaceRepository,
        cache_service: TaskCacheService | None = None,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.task_repository = task_repository
        self.workspace_repository = workspace_repository
        self.cache_service = cache_service or TaskCacheService()

    async def _require_project(self, project_id: int) -> Project:
        project = await self.project_repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)
        return project

    async def _require_label(self, label_id: int) -> Label:
        label = await self.repository.get(label_id)
        if label is None:
            raise NotFoundException(LABEL_NOT_FOUND)
        return label

    async def _require_task(self, task_id: int) -> Task:
        task = await self.task_repository.get(task_id)
        if task is None:
            raise NotFoundException(TASK_NOT_FOUND)
        return task

    async def create(self, project_id: int, payload: LabelCreate, user: User) -> Label:
        project = await self._require_project(project_id)
        await require_project_access(
            self.workspace_repository, project, user, write=True
        )
        existing = await self.repository.get_by_project_and_name(
            project_id, payload.name
        )
        if existing is not None:
            raise ConflictException(LABEL_ALREADY_EXISTS)
        return await self.repository.create(
            Label(project_id=project_id, name=payload.name, color=payload.color)
        )

    async def list_by_project(self, project_id: int, user: User) -> list[Label]:
        project = await self._require_project(project_id)
        await require_project_access(
            self.workspace_repository, project, user, write=False
        )
        return await self.repository.list_by_project(project_id)

    async def update(self, label_id: int, payload: LabelUpdate, user: User) -> Label:
        label = await self._require_label(label_id)
        project = await self._require_project(label.project_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=True,
            forbidden_message=LABEL_FORBIDDEN,
        )
        values = payload.model_dump(exclude_unset=True)
        if "name" in values:
            existing = await self.repository.get_by_project_and_name(
                label.project_id, values["name"]
            )
            if existing is not None and existing.id != label.id:
                raise ConflictException(LABEL_ALREADY_EXISTS)
        if not values:
            return label
        updated = await self.repository.update(label, values)
        await self.cache_service.invalidate_project_tasks(label.project_id)
        return updated

    async def delete(self, label_id: int, user: User) -> None:
        label = await self._require_label(label_id)
        project = await self._require_project(label.project_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=True,
            forbidden_message=LABEL_FORBIDDEN,
        )
        project_id = label.project_id
        await self.repository.delete(label)
        await self.cache_service.invalidate_project_tasks(project_id)

    async def list_for_task(self, task_id: int, user: User) -> list[Label]:
        task = await self._require_task(task_id)
        project = await self._require_project(task.project_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=False,
            forbidden_message=TASK_FORBIDDEN,
        )
        return await self.repository.list_for_task(task_id)

    async def attach_to_task(
        self, task_id: int, label_id: int, user: User
    ) -> TaskLabelRead:
        task = await self._require_task(task_id)
        project = await self._require_project(task.project_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=True,
            forbidden_message=TASK_FORBIDDEN,
        )
        label = await self._require_label(label_id)
        if label.project_id != task.project_id:
            raise BadRequestException(LABEL_DIFFERENT_PROJECT)
        if await self.repository.is_attached_to_task(task_id, label_id):
            raise ConflictException(LABEL_ALREADY_ATTACHED)
        await self.repository.attach_to_task(task_id, label_id)
        await self.cache_service.invalidate_project_tasks(task.project_id)
        return TaskLabelRead(
            task_id=task.id,
            label_id=label.id,
            name=label.name,
            color=label.color,
        )

    async def detach_from_task(self, task_id: int, label_id: int, user: User) -> None:
        task = await self._require_task(task_id)
        project = await self._require_project(task.project_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=True,
            forbidden_message=TASK_FORBIDDEN,
        )
        if not await self.repository.is_attached_to_task(task_id, label_id):
            raise NotFoundException(TASK_LABEL_NOT_FOUND)
        await self.repository.detach_from_task(task_id, label_id)
        await self.cache_service.invalidate_project_tasks(task.project_id)
