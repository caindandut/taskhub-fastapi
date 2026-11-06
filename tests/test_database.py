import asyncio
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.session import create_database_engine, get_session
from app.main import lifespan
from app.models import Base, User


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "mysql+pymysql://user:secret@localhost/taskhub",
        "mysql+aiomysql://user:pass@word@localhost/taskhub",
        "mysql+aiomysql://user:secret@localhost/",
    ],
)
def test_reject_invalid_or_synchronous_database_url(url: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(database_url=url, _env_file=None)

    assert url not in str(error.value)


def test_database_url_is_hidden_in_settings() -> None:
    settings = Settings(
        database_url="mysql+aiomysql://user:private-password@localhost/taskhub",
        _env_file=None,
    )

    assert "private-password" not in repr(settings)


def test_accept_url_encoded_password() -> None:
    settings = Settings(
        database_url="mysql+aiomysql://user:pass%40word@localhost/taskhub",
        _env_file=None,
    )

    assert settings.database_url.get_secret_value().startswith("mysql+aiomysql://")


def test_async_connection_and_foreign_keys() -> None:
    async def check_connection() -> None:
        engine = create_database_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT 1")) == 1
                assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
        finally:
            await engine.dispose()

    asyncio.run(check_connection())


def test_session_dependency_commits_and_rolls_back() -> None:
    probe_app = FastAPI(lifespan=lifespan)

    @probe_app.post("/users/{name}")
    async def add_user(
        name: str, session: Annotated[AsyncSession, Depends(get_session)]
    ) -> dict[str, str]:
        await session.connection()
        await session.run_sync(lambda sync: Base.metadata.create_all(sync.connection()))
        session.add(
            User(
                email=f"{name}@example.com",
                full_name=name,
                hashed_password="already-hashed-password",
            )
        )
        await session.flush()
        if name == "rollback":
            raise HTTPException(400, "Abort transaction")
        return {"name": name}

    @probe_app.get("/users/count")
    async def count_users(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> int:
        return await session.scalar(select(func.count()).select_from(User))

    with TestClient(probe_app) as client:
        assert client.post("/users/committed").status_code == 200
        assert client.post("/users/rollback").status_code == 400
        assert client.get("/users/count").json() == 1
