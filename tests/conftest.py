import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import create_database_engine
from app.models import Base, Project, User, Workspace

TEST_JWT_SECRET = "test-secret-key-with-at-least-32-bytes!"
TEST_USER_PASSWORD = "StrongPassword123!"
TEST_PASSWORD_HASH = hash_password(TEST_USER_PASSWORD)


@pytest.fixture(autouse=True)
def test_database_url(monkeypatch: pytest.MonkeyPatch):
    get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    yield
    get_settings.cache_clear()


@pytest.fixture
def database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_database_url: None
) -> str:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'taskhub.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    async def prepare_database() -> None:
        engine = create_database_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                owner = User(
                    id=1,
                    email="owner@example.com",
                    full_name="Owner",
                    hashed_password=TEST_PASSWORD_HASH,
                )
                project = Project(
                    id=1,
                    name="Backend",
                    workspace=Workspace(id=1, name="TaskHub", owner=owner),
                )
                session.add_all(
                    [
                        project,
                        User(
                            id=2,
                            email="member@example.com",
                            full_name="Member",
                            hashed_password=TEST_PASSWORD_HASH,
                        ),
                    ]
                )
        finally:
            await engine.dispose()

    asyncio.run(prepare_database())
    return url
