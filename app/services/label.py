from sqlalchemy.exc import IntegrityError

from app.core.constants import (
    LABEL_ALREADY_ATTACHED,
    LABEL_ALREADY_EXISTS,
    LABEL_DIFFERENT_PROJECT,
    LABEL_FORBIDDEN,
    LABEL_NOT_FOUND,
    TASK_LABEL_NOT_FOUND,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models import Label, User
from app.models.enums import UserRole
from app.repositories.label import LabelRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.label import LabelCreate, LabelUpdate, TaskLabelRead
from app.services.permissions import load_project_for_user, load_task_for_user


class LabelService:
    def __init__(
        self,
        repository: LabelRepository,
        project_repository: ProjectRepository,
        task_repository: TaskRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.task_repository = task_repository
        self.workspace_repository = workspace_repository

    async def _require_label(self, label_id: int) -> Label:
        label = await self.repository.get(label_id)
        if label is None:
            raise NotFoundException(LABEL_NOT_FOUND)
        return label

    async def create(self, project_id: int, payload: LabelCreate, user: User) -> Label:
        await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            project_id,
            user,
            write=True,
        )
        existing = await self.repository.get_by_project_and_name(
            project_id, payload.name
        )
        if existing is not None:
            raise ConflictException(LABEL_ALREADY_EXISTS)
        try:
            async with self.repository.session.begin_nested():
                return await self.repository.create(
                    Label(project_id=project_id, name=payload.name, color=payload.color)
                )
        except IntegrityError as exc:
            raise ConflictException(LABEL_ALREADY_EXISTS) from exc

    async def list_by_project(self, project_id: int, user: User) -> list[Label]:
        await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            project_id,
            user,
            write=False,
        )
        return await self.repository.list_by_project(project_id)

    async def update(self, label_id: int, payload: LabelUpdate, user: User) -> Label:
        label = await self._require_label(label_id)
        await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            label.project_id,
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
        try:
            async with self.repository.session.begin_nested():
                return await self.repository.update(label, values)
        except IntegrityError as exc:
            raise ConflictException(LABEL_ALREADY_EXISTS) from exc

    async def delete(self, label_id: int, user: User) -> None:
        label = await self._require_label(label_id)
        await load_project_for_user(
            self.project_repository,
            self.workspace_repository,
            label.project_id,
            user,
            write=True,
            forbidden_message=LABEL_FORBIDDEN,
        )
        await self.repository.delete(label)

    async def list_for_task(self, task_id: int, user: User) -> list[Label]:
        await load_task_for_user(
            self.task_repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=False,
        )
        return await self.repository.list_for_task(task_id)

    async def attach_to_task(
        self, task_id: int, label_id: int, user: User
    ) -> TaskLabelRead:
        task, _, _ = await load_task_for_user(
            self.task_repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
        )
        label = await self._require_label(label_id)
        if label.project_id != task.project_id:
            label_project = await self.project_repository.get(label.project_id)
            if label_project is None:
                raise NotFoundException(LABEL_NOT_FOUND)
            if user.role != UserRole.ADMIN:
                role = await self.workspace_repository.get_effective_role(
                    label_project.workspace_id, user.id
                )
                if role is None:
                    raise NotFoundException(LABEL_NOT_FOUND)
            raise BadRequestException(LABEL_DIFFERENT_PROJECT)
        if await self.repository.is_attached_to_task(task_id, label_id):
            raise ConflictException(LABEL_ALREADY_ATTACHED)
        try:
            async with self.repository.session.begin_nested():
                await self.repository.attach_to_task(task_id, label_id)
        except IntegrityError as exc:
            raise ConflictException(LABEL_ALREADY_ATTACHED) from exc
        return TaskLabelRead(
            task_id=task.id,
            label_id=label.id,
            name=label.name,
            color=label.color,
        )

    async def detach_from_task(self, task_id: int, label_id: int, user: User) -> None:
        await load_task_for_user(
            self.task_repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
        )
        if not await self.repository.is_attached_to_task(task_id, label_id):
            raise NotFoundException(TASK_LABEL_NOT_FOUND)
        await self.repository.detach_from_task(task_id, label_id)
