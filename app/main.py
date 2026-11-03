from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.endpoints import health
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # No shared resources need initialization or cleanup in session 01.
    yield


app = FastAPI(title="TaskHub API", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(api_router, prefix="/api/v1")
