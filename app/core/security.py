import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.constants import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS,
    INVALID_TOKEN,
    JWT_ALGORITHM_HS256,
)
from app.core.exceptions import AuthenticationException
from app.models.enums import TokenType

password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("taskhub-dummy-password-verification")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(plain_password, hashed_password)
    except (UnknownHashError, ValueError):
        return False


def verify_password_dummy(plain_password: str) -> None:
    password_hash.verify(plain_password, DUMMY_PASSWORD_HASH)


def create_access_token(
    subject: int | str,
    secret_key: str,
    algorithm: str = JWT_ALGORITHM_HS256,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(subject),
        "type": TokenType.ACCESS.value,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_refresh_token(
    subject: int | str,
    secret_key: str,
    algorithm: str = JWT_ALGORITHM_HS256,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(days=DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": str(subject),
        "type": TokenType.REFRESH.value,
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def _decode_token(
    token: str,
    expected_type: TokenType | str,
    secret_key: str,
    algorithm: str = JWT_ALGORITHM_HS256,
) -> int:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm],
            options={"require": ["sub", "exp", "type"]},
        )
    except InvalidTokenError as error:
        raise AuthenticationException(INVALID_TOKEN) from error

    if payload.get("type") != str(expected_type):
        raise AuthenticationException(INVALID_TOKEN)

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise AuthenticationException(INVALID_TOKEN)

    user_id = int(subject)
    if user_id <= 0:
        raise AuthenticationException(INVALID_TOKEN)
    return user_id


def decode_access_token(
    token: str,
    secret_key: str,
    algorithm: str = JWT_ALGORITHM_HS256,
) -> int:
    return _decode_token(
        token=token,
        expected_type=TokenType.ACCESS,
        secret_key=secret_key,
        algorithm=algorithm,
    )


def decode_refresh_token(
    token: str,
    secret_key: str,
    algorithm: str = JWT_ALGORITHM_HS256,
) -> int:
    return _decode_token(
        token=token,
        expected_type=TokenType.REFRESH,
        secret_key=secret_key,
        algorithm=algorithm,
    )
