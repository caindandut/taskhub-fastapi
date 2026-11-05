from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


def create_database_engine(database_url: str) -> AsyncEngine:
    connect_args: dict[str, str | int] = {}
    if database_url.startswith("mysql+aiomysql:"):
        connect_args["init_command"] = "SET time_zone = '+00:00'"
        connect_args["connect_timeout"] = 10
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args=connect_args,
    )
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _connection_record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session, session.begin():
        yield session
