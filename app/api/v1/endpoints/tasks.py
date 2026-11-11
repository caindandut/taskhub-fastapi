from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.constants import DATABASE_CONFLICT, NOT_AUTHENTICATED, TASK_NOT_FOUND
from app.core.dependencies import CurrentUserDep, get_task_service
from app.schemas.task import TaskCreate, TaskPage, TaskQuery, TaskRead, TaskUpdate
from app.services.task import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
TaskID = Annotated[int, Path(gt=0, description="Task ID")]


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        404: {"description": "Related resource not found"},
        409: {"description": DATABASE_CONFLICT},
    },
)
async def create_task(
    payload: TaskCreate,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskRead:
    task = await service.create(payload, creator_id=current_user.id)
    return TaskRead.model_validate(task)


@router.get(
    "",
    response_model=TaskPage,
    summary="List tasks",
    responses={401: {"description": NOT_AUTHENTICATED}},
)
async def list_tasks(
    query: Annotated[TaskQuery, Query()],
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskPage:
    return await service.list(query)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def get_task(
    task_id: TaskID,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskRead:
    task = await service.get(task_id)
    return TaskRead.model_validate(task)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        404: {"description": "Task or assignee not found"},
        409: {"description": DATABASE_CONFLICT},
    },
)
async def update_task(
    task_id: TaskID,
    payload: TaskUpdate,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskRead:
    task = await service.update(task_id, payload)
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def delete_task(
    task_id: TaskID,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> Response:
    await service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
