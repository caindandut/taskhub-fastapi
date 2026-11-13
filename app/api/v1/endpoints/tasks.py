from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.constants import (
    DATABASE_CONFLICT,
    NOT_AUTHENTICATED,
    PROJECT_ARCHIVED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
    TASK_NOT_FOUND,
)
from app.core.dependencies import CurrentUserDep, get_task_service
from app.schemas.task import (
    ProjectTaskCreate,
    ProjectTaskQuery,
    TaskCreate,
    TaskPage,
    TaskQuery,
    TaskRead,
    TaskUpdate,
)
from app.services.task import TaskService

router = APIRouter(tags=["Tasks"])
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
TaskID = Annotated[int, Path(gt=0, description="Task ID")]
ProjectID = Annotated[int, Path(gt=0, description="Project ID")]


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task in project",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
        409: {"description": DATABASE_CONFLICT},
    },
)
async def create_project_task(
    project_id: ProjectID,
    payload: ProjectTaskCreate,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskRead:
    task = await service.create(
        TaskCreate(**payload.model_dump(), project_id=project_id),
        user=current_user,
    )
    return TaskRead.model_validate(task)


@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskPage,
    summary="List tasks in project",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
    },
)
async def list_project_tasks(
    project_id: ProjectID,
    query: Annotated[ProjectTaskQuery, Query()],
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskPage:
    return await service.list_by_project(project_id, query, current_user)


@router.post(
    "/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": "Related resource not found"},
        409: {"description": DATABASE_CONFLICT},
    },
)
async def create_task(
    payload: TaskCreate,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskRead:
    task = await service.create(payload, user=current_user)
    return TaskRead.model_validate(task)


@router.get(
    "/tasks",
    response_model=TaskPage,
    summary="List tasks",
    responses={401: {"description": NOT_AUTHENTICATED}},
)
async def list_tasks(
    query: Annotated[TaskQuery, Query()],
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskPage:
    return await service.list(query, current_user)


@router.get(
    "/tasks/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": TASK_FORBIDDEN},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def get_task(
    task_id: TaskID,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> TaskRead:
    task = await service.get(task_id, current_user)
    return TaskRead.model_validate(task)


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": TASK_FORBIDDEN},
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
    task = await service.update(task_id, payload, current_user)
    return TaskRead.model_validate(task)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": TASK_FORBIDDEN},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def delete_task(
    task_id: TaskID,
    current_user: CurrentUserDep,
    service: TaskServiceDep,
) -> Response:
    await service.delete(task_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
