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
    INCORRECT_CURRENT_PASSWORD,
    INVALID_CREDENTIALS,
    INVALID_TOKEN,
    NOT_AUTHENTICATED,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
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
    assert token_data["refresh_token"]
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


def test_refresh_token_rotation_and_revocation(client: TestClient) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    tokens_1 = login_res.json()
    ref_1 = tokens_1["refresh_token"]

    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": ref_1})
    assert refresh_res.status_code == 200, refresh_res.text
    tokens_2 = refresh_res.json()
    assert tokens_2["access_token"]
    assert tokens_2["refresh_token"]
    assert tokens_2["token_type"] == "bearer"
    ref_2 = tokens_2["refresh_token"]
    assert ref_2 != ref_1

    # New access token works
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens_2['access_token']}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "owner@example.com"

    # Old refresh token is revoked and cannot be used again
    reused_res = client.post("/api/v1/auth/refresh", json={"refresh_token": ref_1})
    assert reused_res.status_code == 401
    assert reused_res.json() == {"detail": INVALID_TOKEN}

    # New refresh token works again
    refresh_res_2 = client.post("/api/v1/auth/refresh", json={"refresh_token": ref_2})
    assert refresh_res_2.status_code == 200


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    ref = login_res.json()["refresh_token"]

    logout_res = client.post("/api/v1/auth/logout", json={"refresh_token": ref})
    assert logout_res.status_code == 204
    assert logout_res.content == b""

    # Refresh with revoked token fails
    refresh_res = client.post("/api/v1/auth/refresh", json={"refresh_token": ref})
    assert refresh_res.status_code == 401
    assert refresh_res.json() == {"detail": INVALID_TOKEN}

    # Logout again with already revoked token fails
    logout_again = client.post("/api/v1/auth/logout", json={"refresh_token": ref})
    assert logout_again.status_code == 401
    assert logout_again.json() == {"detail": INVALID_TOKEN}


def test_refresh_rejects_invalid_tokens(client: TestClient) -> None:
    access_token = create_access_token(subject=1, secret_key=TEST_JWT_SECRET)
    expired_refresh = create_refresh_token(
        subject=1, secret_key=TEST_JWT_SECRET, expires_delta=timedelta(seconds=-1)
    )
    untracked_refresh = create_refresh_token(
        subject=1, secret_key=TEST_JWT_SECRET, expires_delta=timedelta(days=1)
    )

    for token in ("invalid.token", access_token, expired_refresh, untracked_refresh):
        res = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert res.status_code == 401
        assert res.json() == {"detail": INVALID_TOKEN}


def test_refresh_rejects_inactive_user(client: TestClient, database_url: str) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "member@example.com", "password": TEST_USER_PASSWORD},
    )
    ref = login_res.json()["refresh_token"]

    async def deactivate() -> None:
        engine = create_database_engine(database_url)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory.begin() as session:
                user = await session.get(User, 2)
                assert user is not None
                user.is_active = False
        finally:
            await engine.dispose()

    asyncio.run(deactivate())

    res = client.post("/api/v1/auth/refresh", json={"refresh_token": ref})
    assert res.status_code == 401
    assert res.json() == {"detail": INACTIVE_USER}


def test_update_user_profile(client: TestClient) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Unauthenticated fails
    assert (
        client.patch("/api/v1/users/me", json={"full_name": "Test"}).status_code == 401
    )

    # Update full_name
    patch_res = client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"full_name": "  Renamed Owner  "},
    )
    assert patch_res.status_code == 200, patch_res.text
    profile = patch_res.json()
    assert profile["full_name"] == "Renamed Owner"
    assert profile["email"] == "owner@example.com"

    # Confirmed by GET
    get_res = client.get("/api/v1/users/me", headers=headers)
    assert get_res.json()["full_name"] == "Renamed Owner"

    # Empty payload preserves existing
    empty_patch = client.patch("/api/v1/users/me", headers=headers, json={})
    assert empty_patch.status_code == 200
    assert empty_patch.json()["full_name"] == "Renamed Owner"


@pytest.mark.parametrize(
    "payload",
    [
        {"full_name": None},
        {"full_name": "   "},
        {"email": "changed@example.com"},
        {"role": "ADMIN"},
        {"is_active": False},
        {"id": 99},
        {"password": "NewPassword123!"},
        {"hashed_password": "NewPassword123!"},
    ],
)
def test_update_user_profile_rejects_invalid_and_forbidden_fields(
    client: TestClient, payload: dict
) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}
    res = client.patch("/api/v1/users/me", headers=headers, json=payload)
    assert res.status_code == 422


def test_change_password_success_and_revocation(client: TestClient) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    old_tokens = login_res.json()
    headers = {"Authorization": f"Bearer {old_tokens['access_token']}"}
    ref = old_tokens["refresh_token"]

    # Change password
    new_password = "BrandNewPassword123!"
    for path in ("/api/v1/auth/change-password", "/api/v1/users/me/change-password"):
        pass

    change_res = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": TEST_USER_PASSWORD,
            "new_password": new_password,
        },
    )
    assert change_res.status_code == 204
    assert change_res.content == b""

    # Old password no longer works for login
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    assert old_login.status_code == 401

    # New password works
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": new_password},
    )
    assert new_login.status_code == 200

    # Old refresh token was revoked upon password change
    old_ref_res = client.post("/api/v1/auth/refresh", json={"refresh_token": ref})
    assert old_ref_res.status_code == 401
    assert old_ref_res.json() == {"detail": INVALID_TOKEN}

    # Change password back via /users/me/change-password to verify both routes
    new_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}
    change_back = client.post(
        "/api/v1/users/me/change-password",
        headers=new_headers,
        json={
            "current_password": new_password,
            "new_password": TEST_USER_PASSWORD,
        },
    )
    assert change_back.status_code == 204


def test_change_password_validations(client: TestClient) -> None:
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": TEST_USER_PASSWORD},
    )
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Unauthenticated
    assert (
        client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": "NewValidPassword123!",
            },
        ).status_code
        == 401
    )

    # Wrong current password
    wrong_curr = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "WrongCurrentPassword123!",
            "new_password": "NewValidPassword123!",
        },
    )
    assert wrong_curr.status_code == 401
    assert wrong_curr.json() == {"detail": INCORRECT_CURRENT_PASSWORD}

    # Validation errors on new password
    for bad_new in ("short", "        ", ""):
        bad_res = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={
                "current_password": TEST_USER_PASSWORD,
                "new_password": bad_new,
            },
        )
        assert bad_res.status_code == 422

    # Extra forbidden field
    extra_res = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": TEST_USER_PASSWORD,
            "new_password": "NewValidPassword123!",
            "extra": "forbidden",
        },
    )
    assert extra_res.status_code == 422
