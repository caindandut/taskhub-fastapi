from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.exceptions import AppException
from app.repositories.task import TaskRepository


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    repository = TaskRepository()
    app.state.task_repository = repository
    app.state.tasks = repository._store
    try:
        yield
    finally:
        repository.clear()


app = FastAPI(title="TaskHub API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Global handler for application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


app.include_router(api_router, prefix="/api/v1")
