from typing import Annotated

from pydantic import ConfigDict, Field, PositiveInt, field_validator

from app.core.constants import (
    DEFAULT_LABEL_COLOR,
    FIELD_CANNOT_BE_NULL,
    LABEL_NAME_MAX_LENGTH,
    LABEL_NAME_MIN_LENGTH,
)
from app.schemas.base import BaseSchema

LabelName = Annotated[
    str, Field(min_length=LABEL_NAME_MIN_LENGTH, max_length=LABEL_NAME_MAX_LENGTH)
]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class LabelCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: LabelName
    color: HexColor = DEFAULT_LABEL_COLOR


class LabelUpdate(BaseSchema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
