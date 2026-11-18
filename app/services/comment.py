from app.core.constants import (
    COMMENT_FORBIDDEN,
    COMMENT_NOT_FOUND,
    PROJECT_ARCHIVED,
)
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.models import Comment, User
from app.models.enums import ProjectStatus, WorkspaceRole
from app.repositories.comment import CommentRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.comment import CommentCreate, CommentPage, CommentQuery, CommentRead
from app.services.permissions import load_task_for_user


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

    async def create(self, task_id: int, payload: CommentCreate, user: User) -> Comment:
        await load_task_for_user(
            self.task_repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=True,
            forbidden_message=COMMENT_FORBIDDEN,
        )
        return await self.repository.create(
            Comment(task_id=task_id, author_id=user.id, content=payload.content)
        )

    async def list_by_task(
        self, task_id: int, query: CommentQuery, user: User
    ) -> CommentPage:
        await load_task_for_user(
            self.task_repository,
            self.project_repository,
            self.workspace_repository,
            task_id,
            user,
            write=False,
            forbidden_message=COMMENT_FORBIDDEN,
        )
        comments, total = await self.repository.list_by_task(task_id, query)
        return CommentPage(
            items=[CommentRead.model_validate(comment) for comment in comments],
            total=total,
            page=query.page,
            limit=query.limit,
        )

    async def delete(self, comment_id: int, user: User) -> None:
        comment = await self.repository.get(comment_id)
        if comment is None:
            raise NotFoundException(COMMENT_NOT_FOUND)
        _, project, effective_role = await load_task_for_user(
            self.task_repository,
            self.project_repository,
            self.workspace_repository,
            comment.task_id,
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
