import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.constants import DEFAULT_APP_NAME, DEFAULT_APP_VERSION
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import DynamicCORSMiddleware, RequestContextMiddleware
from app.core.openapi import configure_openapi
from app.db.session import create_database_engine
from app.services.cache import create_redis_client

logger = logging.getLogger(__name__)


def create_lifespan(
    explicit_settings: Settings | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = explicit_settings or get_settings()
        configure_logging(
            log_level=settings.log_level,
            log_format=settings.log_format,
        )
        engine = create_database_engine(settings.database_url.get_secret_value())
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        redis_client = (
            create_redis_client(settings.redis_url) if settings.redis_url else None
        )
        app.state.redis_client = redis_client
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            logger.info(
                "Application started (env=%s, redis_enabled=%s)",
                settings.app_env,
                redis_client is not None,
            )
            yield
        finally:
            if redis_client is not None:
                await redis_client.aclose()
            await engine.dispose()
            logger.info("Application shut down")

    return lifespan


lifespan = create_lifespan()


def create_app(settings: Settings | None = None) -> FastAPI:
    title = settings.app_name if settings is not None else DEFAULT_APP_NAME
    version = settings.app_version if settings is not None else DEFAULT_APP_VERSION
    application = FastAPI(
        title=title,
        version=version,
        lifespan=create_lifespan(settings),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={"persistAuthorization": True},
    )

    # Outer RequestContextMiddleware wraps DynamicCORSMiddleware so preflights and
    # errors also carry X-Request-ID, timing headers, and access logs.
    application.add_middleware(DynamicCORSMiddleware, settings=settings)
    application.add_middleware(RequestContextMiddleware)

    register_exception_handlers(application)
    application.include_router(api_router, prefix="/api/v1")
    configure_openapi(application)
    return application


app = create_app()
