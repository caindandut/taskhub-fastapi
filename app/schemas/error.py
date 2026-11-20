from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class ErrorResponse(BaseSchema):
    detail: str = Field(
        description="Human-readable error description.",
        examples=["Resource not found"],
    )


class ValidationErrorDetail(BaseSchema):
    loc: list[str | int] = Field(
        description="Location of the invalid field.",
        examples=[["body", "title"]],
    )
    msg: str = Field(
        description="Validation failure message.",
        examples=["Field required"],
    )
    type: str = Field(
        description="Machine-readable Pydantic error type.",
        examples=["missing"],
    )
    ctx: dict[str, Any] | None = Field(
        default=None,
        description="Optional validation context metadata.",
    )


class ValidationErrorResponse(BaseSchema):
    detail: list[ValidationErrorDetail] = Field(
        description="List of sanitized field validation errors.",
    )
