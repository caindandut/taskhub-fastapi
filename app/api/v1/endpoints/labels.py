from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from app.core.constants import (
    DATABASE_CONFLICT,
    LABEL_ALREADY_ATTACHED,
    LABEL_ALREADY_EXISTS,
    LABEL_DIFFERENT_PROJECT,
    LABEL_FORBIDDEN,
    LABEL_NOT_FOUND,
    NOT_AUTHENTICATED,
    PROJECT_ARCHIVED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
    TASK_LABEL_NOT_FOUND,
    TASK_NOT_FOUND,
)
from app.core.dependencies import CurrentUserDep, get_label_service
from app.models import Label
from app.schemas.label import LabelCreate, LabelRead, LabelUpdate, TaskLabelRead
from app.services.label import LabelService

router = APIRouter(tags=["Labels"])
LabelServiceDep = Annotated[LabelService, Depends(get_label_service)]
ProjectID = Annotated[int, Path(gt=0, description="Project ID")]
LabelID = Annotated[int, Path(gt=0, description="Label ID")]
TaskID = Annotated[int, Path(gt=0, description="Task ID")]


@router.post(
    "/projects/{project_id}/labels",
    response_model=LabelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a label in project",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
        409: {"description": f"{LABEL_ALREADY_EXISTS} / {DATABASE_CONFLICT}"},
    },
)
async def create_label(
    project_id: ProjectID,
    payload: LabelCreate,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> Label:
    return await service.create(project_id, payload, current_user)


@router.get(
    "/projects/{project_id}/labels",
    response_model=list[LabelRead],
    summary="List labels in project",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": PROJECT_FORBIDDEN},
        404: {"description": PROJECT_NOT_FOUND},
    },
)
async def list_project_labels(
    project_id: ProjectID,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> list[Label]:
    return await service.list_by_project(project_id, current_user)


@router.patch(
    "/labels/{label_id}",
    response_model=LabelRead,
    summary="Update a label",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": LABEL_FORBIDDEN},
        404: {"description": LABEL_NOT_FOUND},
        409: {"description": LABEL_ALREADY_EXISTS},
    },
)
async def update_label(
    label_id: LabelID,
    payload: LabelUpdate,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> Label:
    return await service.update(label_id, payload, current_user)


@router.delete(
    "/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a label",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": LABEL_FORBIDDEN},
        404: {"description": LABEL_NOT_FOUND},
    },
)
async def delete_label(
    label_id: LabelID,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> Response:
    await service.delete(label_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/tasks/{task_id}/labels",
    response_model=list[LabelRead],
    summary="List labels attached to a task",
    responses={
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": TASK_FORBIDDEN},
        404: {"description": TASK_NOT_FOUND},
    },
)
async def list_task_labels(
    task_id: TaskID,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> list[Label]:
    return await service.list_for_task(task_id, current_user)


@router.post(
    "/tasks/{task_id}/labels/{label_id}",
    response_model=TaskLabelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a label to a task",
    responses={
        400: {"description": f"{PROJECT_ARCHIVED} / {LABEL_DIFFERENT_PROJECT}"},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": TASK_FORBIDDEN},
        404: {"description": f"{TASK_NOT_FOUND} / {LABEL_NOT_FOUND}"},
        409: {"description": LABEL_ALREADY_ATTACHED},
    },
)
async def attach_label_to_task(
    task_id: TaskID,
    label_id: LabelID,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> TaskLabelRead:
    return await service.attach_to_task(task_id, label_id, current_user)


@router.delete(
    "/tasks/{task_id}/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a label from a task",
    responses={
        400: {"description": PROJECT_ARCHIVED},
        401: {"description": NOT_AUTHENTICATED},
        403: {"description": TASK_FORBIDDEN},
        404: {"description": f"{TASK_NOT_FOUND} / {TASK_LABEL_NOT_FOUND}"},
    },
)
async def detach_label_from_task(
    task_id: TaskID,
    label_id: LabelID,
    current_user: CurrentUserDep,
    service: LabelServiceDep,
) -> Response:
    await service.detach_from_task(task_id, label_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
