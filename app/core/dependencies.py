from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.constants import NOT_AUTHENTICATED
from app.core.exceptions import AuthenticationException
from app.db.session import get_session
from app.models import User
from app.repositories.comment import CommentRepository
from app.repositories.label import LabelRepository
from app.repositories.project import ProjectRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.task import TaskRepository
from app.repositories.user import UserRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.auth import AuthService
from app.services.cache import TaskCacheService
from app.services.comment import CommentService
from app.services.label import LabelService
from app.services.project import ProjectService
from app.services.task import TaskService
from app.services.workspace import WorkspaceService

SessionDep = Annotated[AsyncSession, Depends(get_session, scope="function")]
bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository(session: SessionDep) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_auth_service(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    token_repository: Annotated[
        RefreshTokenRepository, Depends(get_refresh_token_repository)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(user_repository, token_repository, settings)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials.strip()
    ):
        raise AuthenticationException(NOT_AUTHENTICATED)
    return await service.get_current_user(credentials.credentials.strip())


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def get_workspace_repository(session: SessionDep) -> WorkspaceRepository:
    return WorkspaceRepository(session)


def get_workspace_service(
    repository: Annotated[WorkspaceRepository, Depends(get_workspace_repository)],
) -> WorkspaceService:
    return WorkspaceService(repository)


def get_redis_client(request: Request) -> Redis | None:
    return getattr(request.app.state, "redis_client", None)


def get_task_cache_service(
    redis_client: Annotated[Redis | None, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TaskCacheService:
    return TaskCacheService(
        redis_client=redis_client,
        ttl_seconds=settings.task_cache_ttl_seconds,
    )


def get_project_repository(session: SessionDep) -> ProjectRepository:
    return ProjectRepository(session)


def get_project_service(
    repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    workspace_repository: Annotated[
        WorkspaceRepository, Depends(get_workspace_repository)
    ],
    cache_service: Annotated[TaskCacheService, Depends(get_task_cache_service)],
) -> ProjectService:
    return ProjectService(repository, workspace_repository, cache_service)


def get_task_repository(session: SessionDep) -> TaskRepository:
    return TaskRepository(session)


def get_task_service(
    repository: Annotated[TaskRepository, Depends(get_task_repository)],
    workspace_repository: Annotated[
        WorkspaceRepository, Depends(get_workspace_repository)
    ],
    cache_service: Annotated[TaskCacheService, Depends(get_task_cache_service)],
) -> TaskService:
    return TaskService(repository, workspace_repository, cache_service)


def get_label_repository(session: SessionDep) -> LabelRepository:
    return LabelRepository(session)


def get_label_service(
    repository: Annotated[LabelRepository, Depends(get_label_repository)],
    project_repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    workspace_repository: Annotated[
        WorkspaceRepository, Depends(get_workspace_repository)
    ],
    cache_service: Annotated[TaskCacheService, Depends(get_task_cache_service)],
) -> LabelService:
    return LabelService(
        repository,
        project_repository,
        task_repository,
        workspace_repository,
        cache_service,
    )


def get_comment_repository(session: SessionDep) -> CommentRepository:
    return CommentRepository(session)


def get_comment_service(
    repository: Annotated[CommentRepository, Depends(get_comment_repository)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    project_repository: Annotated[ProjectRepository, Depends(get_project_repository)],
    workspace_repository: Annotated[
        WorkspaceRepository, Depends(get_workspace_repository)
    ],
) -> CommentService:
    return CommentService(
        repository, task_repository, project_repository, workspace_repository
    )
