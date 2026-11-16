from app.core.constants import (
    COMMENT_FORBIDDEN,
    COMMENT_NOT_FOUND,
    PROJECT_ARCHIVED,
    PROJECT_NOT_FOUND,
    TASK_NOT_FOUND,
)
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.models import Comment, Project, Task, User
from app.models.enums import ProjectStatus, WorkspaceRole
from app.repositories.comment import CommentRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.comment import CommentCreate
from app.services.permissions import require_project_access


class CommentService:
    def __init__(
        self,
        repository: CommentRepository,
        task_repository: TaskRepository,
        project_repository: ProjectRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.repository = repository
        self.task_repository = task_repository
        self.project_repository = project_repository
        self.workspace_repository = workspace_repository

    async def _require_task_and_project(self, task_id: int) -> tuple[Task, Project]:
        task = await self.task_repository.get(task_id)
        if task is None:
            raise NotFoundException(TASK_NOT_FOUND)
        project = await self.project_repository.get(task.project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)
        return task, project

    async def create(self, task_id: int, payload: CommentCreate, user: User) -> Comment:
        _, project = await self._require_task_and_project(task_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=True,
            forbidden_message=COMMENT_FORBIDDEN,
        )
        return await self.repository.create(
            Comment(task_id=task_id, author_id=user.id, content=payload.content)
        )

    async def list_by_task(self, task_id: int, user: User) -> list[Comment]:
        _, project = await self._require_task_and_project(task_id)
        await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=False,
            forbidden_message=COMMENT_FORBIDDEN,
        )
        return await self.repository.list_by_task(task_id)

    async def delete(self, comment_id: int, user: User) -> None:
        comment = await self.repository.get(comment_id)
        if comment is None:
            raise NotFoundException(COMMENT_NOT_FOUND)
        _, project = await self._require_task_and_project(comment.task_id)
        effective_role = await require_project_access(
            self.workspace_repository,
            project,
            user,
            write=True,
            check_archived=False,
            forbidden_message=COMMENT_FORBIDDEN,
        )
        if effective_role != WorkspaceRole.OWNER and comment.author_id != user.id:
            raise ForbiddenException(COMMENT_FORBIDDEN)
        if project.status == ProjectStatus.ARCHIVED:
            raise BadRequestException(PROJECT_ARCHIVED)
        await self.repository.delete(comment)
