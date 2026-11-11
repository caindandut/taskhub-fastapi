from app.core.constants import TASK_LIMIT_DEFAULT
from app.schemas.task import TaskCreate, TaskPatch, TaskRead, TaskUpdate


class TaskRepository:
    """In-memory task repository with monotonic ID generation."""

    def __init__(self, initial_tasks: dict[int, TaskRead] | None = None) -> None:
        self._store: dict[int, TaskRead] = dict(initial_tasks) if initial_tasks else {}
        self._next_id: int = max(self._store.keys(), default=0) + 1

    def create(self, payload: TaskCreate) -> TaskRead:
        task_id = self._next_id
        self._next_id += 1
        task = TaskRead(id=task_id, title=payload.title, description=payload.description)
        self._store[task_id] = task
        return task

    def get(self, task_id: int) -> TaskRead | None:
        return self._store.get(task_id)

    def list(
        self, q: str | None = None, limit: int = TASK_LIMIT_DEFAULT
    ) -> tuple[list[TaskRead], int]:
        tasks = list(self._store.values())
        if q is not None:
            tasks = [task for task in tasks if q.casefold() in task.title.casefold()]
        tasks.sort(key=lambda t: t.id)
        total = len(tasks)
        return tasks[:limit], total

    def update(self, task_id: int, payload: TaskUpdate) -> TaskRead | None:
        if task_id not in self._store:
            return None
        task = TaskRead(id=task_id, title=payload.title, description=payload.description)
        self._store[task_id] = task
        return task

    def patch(self, task_id: int, payload: TaskPatch) -> TaskRead | None:
        existing = self._store.get(task_id)
        if existing is None:
            return None
        updates = payload.model_dump(exclude_unset=True)
        new_title = updates.get("title", existing.title)
        new_desc = updates.get("description", existing.description)
        updated = TaskRead(id=task_id, title=new_title, description=new_desc)
        self._store[task_id] = updated
        return updated

    def delete(self, task_id: int) -> bool:
        if task_id in self._store:
            del self._store[task_id]
            return True
        return False

    def clear(self) -> None:
        self._store.clear()
        self._next_id = 1
