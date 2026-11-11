import asyncio

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

from app.db.session import create_database_engine
from app.models import (
    Base,
    Comment,
    Label,
    Project,
    RefreshToken,
    Task,
    User,
    Workspace,
    WorkspaceMember,
    task_labels,
)


def test_workspace_members_and_projects_persist() -> None:
    async def check_relationships() -> None:
        engine = create_database_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory.begin() as session:
                owner = User(
                    email="owner@example.com",
                    full_name="Workspace owner",
                    hashed_password="already-hashed-password",
                )
                workspace = Workspace(name="TaskHub", owner=owner)
                workspace.members.append(WorkspaceMember(user=owner, role="OWNER"))
                workspace.projects.append(Project(name="Backend"))
                session.add(workspace)
            async with factory() as session:
                workspace = await session.scalar(
                    select(Workspace).options(
                        selectinload(Workspace.owner),
                        selectinload(Workspace.members).selectinload(
                            WorkspaceMember.user
                        ),
                        selectinload(Workspace.projects),
                    )
                )
                assert workspace.owner.email == "owner@example.com"
                assert workspace.members[0].user.id == workspace.owner_id
                assert workspace.members[0].role == "OWNER"
                assert workspace.projects[0].status == "ACTIVE"
                assert workspace.created_at is not None
        finally:
            await engine.dispose()

    asyncio.run(check_relationships())


def test_project_cannot_reference_missing_workspace() -> None:
    async def check_foreign_key() -> None:
        engine = create_database_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine)
            with pytest.raises(IntegrityError):
                async with factory.begin() as session:
                    session.add(Project(workspace_id=999, name="Invalid project"))
        finally:
            await engine.dispose()

    asyncio.run(check_foreign_key())


def test_task_relationships_and_project_delete_cascade() -> None:
    async def check_task_graph() -> None:
        engine = create_database_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory.begin() as session:
                owner = User(
                    email="owner@example.com",
                    full_name="Owner",
                    hashed_password="already-hashed-password",
                )
                project = Project(
                    name="Backend", workspace=Workspace(name="TaskHub", owner=owner)
                )
                task = Task(title="Add database", project=project, creator=owner)
                task.labels.append(
                    Label(name="backend", project=project, color="#123456")
                )
                task.comments.append(Comment(content="Start here", author=owner))
                session.add(task)
            async with factory() as session:
                task = await session.scalar(
                    select(Task).options(
                        selectinload(Task.project),
                        selectinload(Task.labels),
                        selectinload(Task.comments).selectinload(Comment.author),
                        selectinload(Task.creator),
                    )
                )
                assert task.status == "TODO"
                assert task.priority == "MEDIUM"
                assert task.assignee_id is None
                assert task.creator.email == "owner@example.com"
                assert task.labels[0].project_id == task.project_id
                assert task.comments[0].author_id == task.created_by
                project_id = task.project_id
            async with factory.begin() as session:
                await session.execute(delete(Project).where(Project.id == project_id))
            async with factory() as session:
                for model in (Task, Label, Comment, task_labels):
                    assert (
                        await session.scalar(select(func.count()).select_from(model))
                        == 0
                    )
                assert await session.scalar(select(func.count()).select_from(User)) == 1
        finally:
            await engine.dispose()

    asyncio.run(check_task_graph())


def test_refresh_token_relationship_and_user_delete_cascade() -> None:
    async def check_tokens() -> None:
        from datetime import UTC, datetime, timedelta

        engine = create_database_engine("sqlite+aiosqlite:///:memory:")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with factory.begin() as session:
                user = User(
                    email="tokenuser@example.com",
                    full_name="Token User",
                    hashed_password="already-hashed-password",
                )
                user.refresh_tokens.append(
                    RefreshToken(
                        token_hash="fakehash123",
                        expires_at=datetime.now(UTC).replace(tzinfo=None)
                        + timedelta(days=7),
                    )
                )
                session.add(user)
            async with factory() as session:
                token = await session.scalar(
                    select(RefreshToken).options(selectinload(RefreshToken.user))
                )
                assert token is not None
                assert token.user.email == "tokenuser@example.com"
                user_id = token.user_id
            async with factory.begin() as session:
                await session.execute(delete(User).where(User.id == user_id))
            async with factory() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(RefreshToken))
                    == 0
                )
        finally:
            await engine.dispose()

    asyncio.run(check_tokens())
