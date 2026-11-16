from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.core.constants import (
    COMMENT_FORBIDDEN,
    COMMENT_NOT_FOUND,
    NOT_AUTHENTICATED,
    PROJECT_ARCHIVED,
    TASK_NOT_FOUND,
)
from app.core.dependencies import CurrentUserDep, get_comment_service
from app.schemas.comment import CommentCreate, CommentRead
from app.services.comment import CommentService

router = APIRouter(tags=["Comments"])
CommentServiceDep = Annotated[CommentService, Depends(get_comment_service)]
TaskID = Annotated[int, Path(gt=0, description="Task ID")]
CommentID = Annotated[int, Path(gt=0, description="Comment ID")]


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to a task",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": COMMENT_FORBIDDEN},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def create_comment(
    task_id: TaskID,
    payload: CommentCreate,
    current_user: CurrentUserDep,
    service: CommentServiceDep,
) -> CommentRead:
    comment = await service.create(task_id, payload, current_user)
    return CommentRead.model_validate(comment)


@router.get(
    "/tasks/{task_id}/comments",
    response_model=list[CommentRead],
    summary="List comments on a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": COMMENT_FORBIDDEN},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def list_task_comments(
    task_id: TaskID,
    current_user: CurrentUserDep,
    service: CommentServiceDep,
) -> list[CommentRead]:
    comments = await service.list_by_task(task_id, current_user)
    return [CommentRead.model_validate(comment) for comment in comments]


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": COMMENT_FORBIDDEN},
        404: {"description": COMMENT_NOT_FOUND},
    },
)
async def delete_comment(
    comment_id: CommentID,
    current_user: CurrentUserDep,
    service: CommentServiceDep,
) -> Response:
    await service.delete(comment_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
