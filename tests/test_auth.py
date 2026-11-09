import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.constants import (
    EMAIL_ALREADY_REGISTERED,
    INACTIVE_USER,
    INVALID_CREDENTIALS,
    INVALID_TOKEN,
    NOT_AUTHENTICATED,
)
from app.core.security import create_access_token, verify_password
from app.db.session import create_database_engine
from app.main import app
from app.models import User
from tests.conftest import TEST_JWT_SECRET, TEST_USER_PASSWORD


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_register_hashes_password_and_hides_secrets(
    client: TestClient, database_url: str
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "  New.User@Example.com  ",
            "full_name": "  New User  ",
            "password": "MySecretPassword123!",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.user@example.com"
    assert body["full_name"] == "New User"
    assert body["role"] == "MEMBER"
    assert body["is_active"] is True
    assert body["id"] > 0
    assert body["created_at"]
    assert "password" not in body
    assert "hashed_password" not in body

    async def verify_stored_user() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                user = await session.scalar(
                    select(User).where(User.email == "new.user@example.com")
                )
                assert user is not None
                assert user.hashed_password != "MySecretPassword123!"
                assert verify_password("MySecretPassword123!", user.hashed_password)
                assert not verify_password("WrongPassword123!", user.hashed_password)
        finally:
            await engine.dispose()

    asyncio.run(verify_stored_user())


def test_register_rejects_duplicate_email_case_insensitively(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "OWNER@EXAMPLE.COM",
            "full_name": "Duplicate Owner",
            "password": "AnotherPassword123!",
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": EMAIL_ALREADY_REGISTERED}


@pytest.mark.parametrize(
    "payload",
    [
        {
            "email": "admin-attempt@example.com",
            "full_name": "Attacker",
            "password": "ValidPassword123!",
            "role": "ADMIN",
        },
        {
            "email": "inactive-attempt@example.com",
            "full_name": "Attacker",
            "password": "ValidPassword123!",
            "is_active": False,
        },
        {
            "email": "hash-attempt@example.com",
            "full_name": "Attacker",
            "password": "ValidPassword123!",
            "hashed_password": "injected",
        },
        {
            "email": "id-attempt@example.com",
            "full_name": "Attacker",
            "password": "ValidPassword123!",
            "id": 999,
        },
        {
            "email": "not-an-email",
            "full_name": "Valid Name",
            "password": "ValidPassword123!",
        },
        {
            "email": "short-pass@example.com",
            "full_name": "Valid Name",
            "password": "short",
        },
        {
            "email": "blank-pass@example.com",
            "full_name": "Valid Name",
            "password": "        ",
        },
        {
            "email": "blank-name@example.com",
            "full_name": "   ",
            "password": "ValidPassword123!",
        },
    ],
)
def test_register_rejects_privilege_escalation_and_invalid_fields(
    client: TestClient, payload: dict
) -> None:
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


def test_login_and_fetch_current_user(client: TestClient) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "  OWNER@example.com ", "password": TEST_USER_PASSWORD},
    )
    assert login_response.status_code == 200, login_response.text
    token_data = login_response.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["access_token"]
    assert "password" not in token_data
    assert "hashed_password" not in token_data

    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    for path in ("/api/v1/auth/me", "/api/v1/users/me"):
        me_response = client.get(path, headers=headers)
        assert me_response.status_code == 200
        profile = me_response.json()
        assert profile["id"] == 1
        assert profile["email"] == "owner@example.com"
        assert profile["full_name"] == "Owner"
        assert profile["role"] == "MEMBER"
        assert profile["is_active"] is True
        assert "password" not in profile
        assert "hashed_password" not in profile


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("owner@example.com", "WrongPassword123!"),
        ("missing@example.com", TEST_USER_PASSWORD),
    ],
)
def test_login_rejects_invalid_credentials(
    client: TestClient, email: str, password: str
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_CREDENTIALS}
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_inactive_user_cannot_login_or_access_protected_endpoints(
    client: TestClient, database_url: str
) -> None:
    token = create_access_token(subject=2, secret_key=TEST_JWT_SECRET)

    async def deactivate_member() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                user = await session.get(User, 2)
                assert user is not None
                user.is_active = False
        finally:
            await engine.dispose()

    asyncio.run(deactivate_member())

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": TEST_USER_PASSWORD},
    )
    assert login_response.status_code == 401
    assert login_response.json() == {"detail": INACTIVE_USER}

    headers = {"Authorization": f"Bearer {token}"}
    for path in ("/api/v1/auth/me", "/api/v1/users/me", "/api/v1/tasks"):
        response = client.get(path, headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": INACTIVE_USER}
        assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_missing_or_non_bearer_authorization_returns_401(client: TestClient) -> None:
    for headers in ({}, {"Authorization": "Basic dXNlcjpwYXNz"}):
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 401
        assert response.json() == {"detail": NOT_AUTHENTICATED}
        assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_invalid_or_expired_tokens_return_401(client: TestClient) -> None:
    expired_token = create_access_token(
        subject=1,
        secret_key=TEST_JWT_SECRET,
        expires_delta=timedelta(seconds=-10),
    )
    wrong_secret_token = create_access_token(
        subject=1,
        secret_key="different-secret-key-at-least-32-bytes!",
    )
    wrong_type_token = jwt.encode(
        {
            "sub": "1",
            "type": "refresh",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    non_numeric_sub_token = jwt.encode(
        {
            "sub": "not-an-id",
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )
    deleted_user_token = create_access_token(subject=999, secret_key=TEST_JWT_SECRET)

    for token in (
        "malformed.token.value",
        expired_token,
        wrong_secret_token,
        wrong_type_token,
        non_numeric_sub_token,
        deleted_user_token,
    ):
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json() == {"detail": INVALID_TOKEN}
        assert response.headers.get("WWW-Authenticate") == "Bearer"
