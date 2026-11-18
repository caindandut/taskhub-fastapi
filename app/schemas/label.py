from typing import Annotated

from pydantic import ConfigDict, Field, PositiveInt, field_validator

from app.core.constants import (
    DEFAULT_LABEL_COLOR,
    LABEL_COLOR_LENGTH,
    LABEL_COLOR_PATTERN,
    LABEL_NAME_MAX_LENGTH,
    LABEL_NAME_MIN_LENGTH,
)
from app.core.messages import FIELD_CANNOT_BE_NULL
from app.schemas.base import BaseSchema

LabelName = Annotated[
    str, Field(min_length=LABEL_NAME_MIN_LENGTH, max_length=LABEL_NAME_MAX_LENGTH)
]
HexColor = Annotated[
    str,
    Field(
        min_length=LABEL_COLOR_LENGTH,
        max_length=LABEL_COLOR_LENGTH,
        pattern=LABEL_COLOR_PATTERN,
    ),
]


class LabelCreate(BaseSchema):
    name: LabelName
    color: HexColor = DEFAULT_LABEL_COLOR


class LabelUpdate(BaseSchema):
    name: LabelName | None = None
    color: HexColor | None = None

    @field_validator("name", "color")
    @classmethod
    def reject_explicit_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError(FIELD_CANNOT_BE_NULL)
        return value


class LabelRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    project_id: PositiveInt
    name: str
    color: str


class TaskLabelRead(BaseSchema):
    task_id: PositiveInt
    label_id: PositiveInt
    name: str
    color: str
