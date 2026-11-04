from fastapi import Request

from app.schemas.task import TaskRead


def get_task_store(request: Request) -> dict[int, TaskRead]:
    """Return this application's in-memory practice data."""
    return request.app.state.tasks
