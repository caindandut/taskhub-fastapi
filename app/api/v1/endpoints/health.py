from fastapi import APIRouter
from pydantic import Field

from app.schemas.base import BaseSchema

router = APIRouter(tags=["Health"])


class HealthResponse(BaseSchema):
    status: str = Field(examples=["ok"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Verify that the API process is responsive.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
