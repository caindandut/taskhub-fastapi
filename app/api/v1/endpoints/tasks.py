from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.constants import DATABASE_CONFLICT, TASK_NOT_FOUND
from app.core.dependencies import get_task_service
from app.models import Task
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
        404: {"description": "Related resource not found"},
        409: {"description": DATABASE_CONFLICT},
    },
)
async def create_task(payload: TaskCreate, service: TaskServiceDep) -> Task:
    return await service.create(payload)


@router.get("", response_model=TaskPage, summary="List tasks")
async def list_tasks(
    query: Annotated[TaskQuery, Query()], service: TaskServiceDep
) -> TaskPage:
    return await service.list(query)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    responses={404: {"description": TASK_NOT_FOUND}},
)
async def get_task(task_id: TaskID, service: TaskServiceDep) -> Task:
    return await service.get(task_id)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    responses={
        404: {"description": "Task or assignee not found"},
        409: {"description": DATABASE_CONFLICT},
    },
)
async def update_task(
    task_id: TaskID, payload: TaskUpdate, service: TaskServiceDep
) -> Task:
    return await service.update(task_id, payload)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    responses={404: {"description": TASK_NOT_FOUND}},
)
async def delete_task(task_id: TaskID, service: TaskServiceDep) -> Response:
    await service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
