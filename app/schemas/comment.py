from datetime import UTC, datetime
from typing import Annotated

from pydantic import ConfigDict, Field, PositiveInt, field_validator

from app.core.constants import COMMENT_CONTENT_MAX_LENGTH, COMMENT_CONTENT_MIN_LENGTH
from app.schemas.base import BaseSchema

CommentContent = Annotated[
    str,
    Field(min_length=COMMENT_CONTENT_MIN_LENGTH, max_length=COMMENT_CONTENT_MAX_LENGTH),
]


class CommentCreate(BaseSchema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: CommentContent


class CommentRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: PositiveInt
    task_id: PositiveInt
    author_id: PositiveInt
    content: str
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
