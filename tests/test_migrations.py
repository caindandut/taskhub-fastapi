import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def run_alembic(database_url: str, *arguments: str) -> str:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_migration_upgrade_check_and_downgrade(tmp_path: Path) -> None:
    database = tmp_path / "taskhub.db"
    url = f"sqlite+aiosqlite:///{database.as_posix()}"

    run_alembic(url, "upgrade", "head")
    run_alembic(url, "check")
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert tables == {
            "alembic_version",
            "users",
            "workspaces",
            "workspace_members",
            "projects",
            "tasks",
            "labels",
            "task_labels",
            "comments",
        }
        connection.execute(
            "INSERT INTO users (email, full_name, hashed_password) VALUES (?, ?, ?)",
            ("owner@example.com", "Owner", "already-hashed-password"),
        )
        assert connection.execute("SELECT role, is_active FROM users").fetchone() == (
            "MEMBER",
            1,
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO users (email, full_name, hashed_password) VALUES (?, ?, ?)",
                ("owner@example.com", "Duplicate", "already-hashed-password"),
            )

    run_alembic(url, "downgrade", "base")
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'alembic_version'"
            ).fetchall()
            == []
        )


def test_migration_generates_mysql_sql_without_connecting() -> None:
    sql = run_alembic(
        "mysql+aiomysql://user:placeholder@127.0.0.1/taskhub",
        "upgrade",
        "head",
        "--sql",
    )

    assert "CREATE TABLE tasks" in sql
    assert "FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE" in sql
    assert "AUTO_INCREMENT" in sql
