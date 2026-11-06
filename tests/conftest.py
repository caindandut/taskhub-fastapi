import asyncio
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import create_database_engine
from app.models import Base, Project, User, Workspace


@pytest.fixture(autouse=True)
def test_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def database_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_database_url: None
) -> str:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'taskhub.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)

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
                    hashed_password="already-hashed-test-password",
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
                            hashed_password="already-hashed-test-password",
                        ),
                    ]
                )
        finally:
            await engine.dispose()

    asyncio.run(prepare_database())
    return url
