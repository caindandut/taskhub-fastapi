from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.constants import DATABASE_CONFLICT
from app.core.exceptions import AppException
from app.db.session import create_database_engine
from app.services.cache import create_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = (
        create_redis_client(settings.redis_url) if settings.redis_url else None
    )
    app.state.redis_client = redis_client
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield
    finally:
        if redis_client is not None:
            await redis_client.aclose()
        await engine.dispose()


app = FastAPI(title="TaskHub API", version="0.1.0", lifespan=lifespan)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, error: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.message},
        headers=error.headers,
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request, error: IntegrityError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT, content={"detail": DATABASE_CONFLICT}
    )


app.include_router(api_router, prefix="/api/v1")
