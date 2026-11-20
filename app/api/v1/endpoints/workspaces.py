from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.constants import (
    NOT_AUTHENTICATED,
    WORKSPACE_FORBIDDEN,
    WORKSPACE_NOT_FOUND,
)
from app.core.dependencies import CurrentUserDep, get_workspace_service
from app.models import Workspace
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberRead,
    WorkspaceMemberUpdate,
    WorkspacePage,
    WorkspaceQuery,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])
WorkspaceServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]
WorkspaceID = Annotated[int, Path(gt=0, description="Workspace ID")]
MemberUserID = Annotated[int, Path(gt=0, description="Member User ID")]


@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
    responses={
        401: {"description": NOT_AUTHENTICATED},
    },
)
async def create_workspace(
    payload: WorkspaceCreate,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> Workspace:
    return await service.create(payload, owner=current_user)


@router.get(
    "",
    response_model=WorkspacePage,
    summary="List workspaces accessible by current user",
    responses={
        401: {"description": NOT_AUTHENTICATED},
    },
)
async def list_workspaces(
    query: Annotated[WorkspaceQuery, Query()],
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> WorkspacePage:
    return await service.list(query, user=current_user)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Get a workspace by ID",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": WORKSPACE_NOT_FOUND},
    },
)
async def get_workspace(
    workspace_id: WorkspaceID,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> Workspace:
    return await service.get(workspace_id, user=current_user)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceRead,
    summary="Update a workspace (Owner or Admin only)",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": WORKSPACE_NOT_FOUND},
    },
)
async def update_workspace(
    workspace_id: WorkspaceID,
    payload: WorkspaceUpdate,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> Workspace:
    return await service.update(workspace_id, payload, user=current_user)


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace (Owner or Admin only)",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": WORKSPACE_NOT_FOUND},
    },
)
async def delete_workspace(
    workspace_id: WorkspaceID,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> Response:
    await service.delete(workspace_id, user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberRead],
    summary="List members of a workspace",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": WORKSPACE_NOT_FOUND},
    },
)
async def list_workspace_members(
    workspace_id: WorkspaceID,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> list[WorkspaceMemberRead]:
    return await service.list_members(workspace_id, user=current_user)


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a member to a workspace (Owner or Admin only)",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": "Workspace or user not found"},
        409: {"description": "User is already a member"},
    },
)
async def add_workspace_member(
    workspace_id: WorkspaceID,
    payload: WorkspaceMemberCreate,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> WorkspaceMemberRead:
    return await service.add_member(workspace_id, payload, user=current_user)


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMemberRead,
    summary="Update a workspace member's role (Owner or Admin only)",
    responses={
        400: {"description": "Cannot modify workspace owner's role"},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": "Workspace or member not found"},
    },
)
async def update_workspace_member_role(
    workspace_id: WorkspaceID,
    user_id: MemberUserID,
    payload: WorkspaceMemberUpdate,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> WorkspaceMemberRead:
    return await service.update_member_role(
        workspace_id, user_id, payload, user=current_user
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a member from a workspace (Owner/Admin or self)",
    responses={
        400: {"description": "Cannot remove the workspace owner"},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": WORKSPACE_FORBIDDEN},
        404: {"description": "Workspace or member not found"},
    },
)
async def remove_workspace_member(
    workspace_id: WorkspaceID,
    user_id: MemberUserID,
    current_user: CurrentUserDep,
    service: WorkspaceServiceDep,
) -> Response:
    await service.remove_member(workspace_id, user_id, user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
