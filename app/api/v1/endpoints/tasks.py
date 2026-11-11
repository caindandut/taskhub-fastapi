from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.core.constants import (
    TASK_LIMIT_DEFAULT,
    TASK_LIMIT_MAX,
    TASK_LIMIT_MIN,
    TASK_QUERY_MAX_LENGTH,
    TASK_QUERY_MIN_LENGTH,
)
from app.core.dependencies import get_task_service
from app.core.messages import TASK_NOT_FOUND
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskPatch,
    TaskRead,
    TaskUpdate,
)
from app.services.task import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
TaskID = Annotated[int, Path(gt=0, description="Task ID")]


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    response_description="Created task",
)
async def create_task(payload: TaskCreate, service: TaskServiceDep) -> TaskRead:
    """Create a practice task. Data is lost when the application restarts."""
    return service.create(payload)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
    response_description="Matching tasks",
)
async def list_tasks(
    service: TaskServiceDep,
    q: Annotated[
        str | None,
        Query(
            min_length=TASK_QUERY_MIN_LENGTH,
            max_length=TASK_QUERY_MAX_LENGTH,
            description="Search in task titles",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=TASK_LIMIT_MIN,
            le=TASK_LIMIT_MAX,
            description="Maximum number of tasks to return",
        ),
    ] = TASK_LIMIT_DEFAULT,
) -> TaskListResponse:
    """List practice tasks, optionally searching titles without case sensitivity."""
    return service.list(q=q, limit=limit)


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    response_description="Requested task",
    responses={404: {"description": TASK_NOT_FOUND}},
)
async def get_task(task_id: TaskID, service: TaskServiceDep) -> TaskRead:
    """Get a practice task by its positive integer ID."""
    return service.get(task_id)


@router.put(
    "/{task_id}",
    response_model=TaskRead,
    summary="Update a task",
    response_description="Updated task",
    responses={404: {"description": TASK_NOT_FOUND}},
)
async def update_task(
    task_id: TaskID, payload: TaskUpdate, service: TaskServiceDep
) -> TaskRead:
    """Update a task completely by ID."""
    return service.update(task_id, payload)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Partially update a task",
    response_description="Partially updated task",
    responses={404: {"description": TASK_NOT_FOUND}},
)
async def patch_task(
    task_id: TaskID, payload: TaskPatch, service: TaskServiceDep
) -> TaskRead:
    """Partially update a task by ID. Cannot set title to null."""
    return service.patch(task_id, payload)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    responses={404: {"description": TASK_NOT_FOUND}},
)
async def delete_task(task_id: TaskID, service: TaskServiceDep) -> Response:
    """Delete a task by ID."""
    service.delete(task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
