from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.constants import (
    NOT_AUTHENTICATED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    WORKSPACE_FORBIDDEN,
    WORKSPACE_NOT_FOUND,
)
from app.core.dependencies import CurrentUserDep, get_project_service
from app.models import Project
from app.models.enums import ProjectStatus
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project import ProjectService

router = APIRouter(tags=["Projects"])
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
WorkspaceID = Annotated[int, Path(gt=0, description="Workspace ID")]
ProjectID = Annotated[int, Path(gt=0, description="Project ID")]


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project in workspace",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": f"{WORKSPACE_FORBIDDEN} / {PROJECT_FORBIDDEN}"},
        404: {"description": WORKSPACE_NOT_FOUND},
    },
)
async def create_project(
    workspace_id: WorkspaceID,
    payload: ProjectCreate,
    current_user: CurrentUserDep,
    service: ProjectServiceDep,
) -> Project:
    return await service.create(workspace_id, payload, current_user)


@router.get(
    "/workspaces/{workspace_id}/projects",
    response_model=list[ProjectRead],
    summary="List projects in workspace",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": WORKSPACE_NOT_FOUND},
    },
)
async def list_workspace_projects(
    workspace_id: WorkspaceID,
    current_user: CurrentUserDep,
    service: ProjectServiceDep,
    status_filter: Annotated[
        ProjectStatus | None,
        Query(alias="status", description="Filter projects by status"),
    ] = None,
) -> list[Project]:
    projects = await service.list_by_workspace(
        workspace_id, current_user, status=status_filter
    )
    return list(projects)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Get project details",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
    },
)
async def get_project(
    project_id: ProjectID,
    current_user: CurrentUserDep,
    service: ProjectServiceDep,
) -> Project:
    return await service.get(project_id, current_user)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Update project details or archive status",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
    },
)
async def update_project(
    project_id: ProjectID,
    payload: ProjectUpdate,
    current_user: CurrentUserDep,
    service: ProjectServiceDep,
) -> Project:
    return await service.update(project_id, payload, current_user)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete project",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
    },
)
async def delete_project(
    project_id: ProjectID,
    current_user: CurrentUserDep,
    service: ProjectServiceDep,
) -> Response:
    await service.delete(project_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
