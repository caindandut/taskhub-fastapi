from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.dependencies import get_task_store
from app.schemas.task import TaskCreate, TaskRead

router = APIRouter(prefix="/tasks", tags=["Tasks"])
TaskStore = Annotated[dict[int, TaskRead], Depends(get_task_store)]


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    response_description="Created task",
)
async def create_task(payload: TaskCreate, store: TaskStore) -> TaskRead:
    """Create a practice task. Data is lost when the application restarts."""
    task = TaskRead(id=max(store, default=0) + 1, **payload.model_dump())
    store[task.id] = task
    return task


@router.get(
    "",
    response_model=list[TaskRead],
    summary="List tasks",
    response_description="Matching tasks",
)
async def list_tasks(
    store: TaskStore,
    q: Annotated[
        str | None,
        Query(min_length=1, max_length=200, description="Search in task titles"),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum number of tasks to return")
    ] = 10,
) -> list[TaskRead]:
    """List practice tasks, optionally searching titles without case sensitivity."""
    tasks = list(store.values())
    if q is not None:
        tasks = [task for task in tasks if q.casefold() in task.title.casefold()]
    return tasks[:limit]


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    summary="Get a task",
    response_description="Requested task",
    responses={404: {"description": "Task not found"}},
)
async def get_task(
    task_id: Annotated[int, Path(gt=0, description="Task ID")], store: TaskStore
) -> TaskRead:
    """Get a practice task by its positive integer ID."""
    task = store.get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task
