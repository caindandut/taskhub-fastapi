from typing import Annotated

from pydantic import ConfigDict, Field, PositiveInt

from app.core.constants import COMMENT_CONTENT_MAX_LENGTH, COMMENT_CONTENT_MIN_LENGTH
from app.schemas.base import BaseSchema, PaginatedPage, PaginationQuery, UtcDatetime

CommentContent = Annotated[
    str,
    Field(min_length=COMMENT_CONTENT_MIN_LENGTH, max_length=COMMENT_CONTENT_MAX_LENGTH),
]


class CommentCreate(BaseSchema):
    content: CommentContent


class CommentRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    task_id: PositiveInt
    author_id: PositiveInt
    content: str
    created_at: UtcDatetime


class CommentQuery(PaginationQuery):
    pass


class CommentPage(PaginatedPage):
    items: list[CommentRead]
