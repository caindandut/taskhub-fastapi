from datetime import UTC, datetime
from typing import Annotated, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PositiveInt

from app.core.constants import DEFAULT_PAGE_SIZE, FIELD_CANNOT_BE_NULL, MAX_PAGE_SIZE

T = TypeVar("T")


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def require_not_null(value: T | None) -> T:
    """Reject explicit JSON null values on non-nullable PATCH fields."""
    if value is None:
        raise ValueError(FIELD_CANNOT_BE_NULL)
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]


class BaseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PaginationQuery(BaseSchema):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class PaginatedPage(BaseSchema):
    total: int = Field(ge=0)
    page: PositiveInt
    limit: PositiveInt
