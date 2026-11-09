from functools import lru_cache

from pydantic import PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.constants import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM_HS256,
    JWT_SECRET_MIN_LENGTH,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    jwt_secret_key: SecretStr
    jwt_algorithm: str = JWT_ALGORITHM_HS256
    access_token_expire_minutes: PositiveInt = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except ArgumentError:
            raise ValueError("DATABASE_URL must be a valid database URL") from None
        if url.drivername not in {"mysql+aiomysql", "sqlite+aiosqlite"}:
            raise ValueError("Use mysql+aiomysql, or sqlite+aiosqlite for tests")
        if url.drivername == "mysql+aiomysql" and (not url.host or "@" in url.host):
            raise ValueError(
                "Provide a MySQL host and URL-encode special characters in credentials"
            )
        if not url.database:
            raise ValueError("DATABASE_URL must include a database name")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if len(secret) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {JWT_SECRET_MIN_LENGTH} characters"
            )
        return SecretStr(secret)

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, value: str) -> str:
        if value != JWT_ALGORITHM_HS256:
            raise ValueError(f"JWT_ALGORITHM must be {JWT_ALGORITHM_HS256}")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
