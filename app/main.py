from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import Settings
from app.db.session import create_database_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.tasks = {}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield
    finally:
        app.state.tasks.clear()
        await engine.dispose()


app = FastAPI(title="TaskHub API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(api_router, prefix="/api/v1")
