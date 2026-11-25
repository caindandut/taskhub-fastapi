import json
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from pydantic import (
    BeforeValidator,
    EmailStr,
    Field,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.constants import (
    DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES,
    DEFAULT_APP_ENV,
    DEFAULT_APP_NAME,
    DEFAULT_APP_VERSION,
    DEFAULT_CORS_ALLOW_HEADERS,
    DEFAULT_CORS_ALLOW_METHODS,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS,
    DEFAULT_SMTP_FROM_EMAIL,
    DEFAULT_SMTP_PORT,
    DEFAULT_TASK_CACHE_TTL_SECONDS,
    JWT_ALGORITHM_HS256,
    JWT_SECRET_MIN_LENGTH,
    VALID_APP_ENVS,
    VALID_LOG_FORMATS,
    VALID_LOG_LEVELS,
)


def _parse_str_list(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError("Must be a valid JSON list or CSV string") from exc
            if not isinstance(parsed, list):
                return parsed
            items: list[object] = parsed
        else:
            items = list(stripped.split(","))
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return value

    result: list[object] = []
    for item in items:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                result.append(cleaned)
        else:
            result.append(item)
    return result


StringListEnv = Annotated[list[str], NoDecode, BeforeValidator(_parse_str_list)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = DEFAULT_APP_NAME
    app_version: str = DEFAULT_APP_VERSION
    app_env: str = DEFAULT_APP_ENV
    log_level: str = DEFAULT_LOG_LEVEL
    log_format: str = DEFAULT_LOG_FORMAT
    cors_origins: StringListEnv = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS)
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: StringListEnv = Field(
        default_factory=lambda: list(DEFAULT_CORS_ALLOW_METHODS)
    )
    cors_allow_headers: StringListEnv = Field(
        default_factory=lambda: list(DEFAULT_CORS_ALLOW_HEADERS)
    )

    database_url: SecretStr
    jwt_secret_key: SecretStr
    jwt_algorithm: str = JWT_ALGORITHM_HS256
    access_token_expire_minutes: PositiveInt = DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES
    refresh_token_expire_days: PositiveInt = DEFAULT_REFRESH_TOKEN_EXPIRE_DAYS
    redis_url: str | None = None
    task_cache_ttl_seconds: PositiveInt = DEFAULT_TASK_CACHE_TTL_SECONDS
    smtp_host: str | None = None
    smtp_port: PositiveInt = DEFAULT_SMTP_PORT
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: EmailStr = DEFAULT_SMTP_FROM_EMAIL
    smtp_use_tls: bool = True

    @field_validator("app_name", "app_version")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Value must not be blank")
        return trimmed

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_APP_ENVS:
            allowed = ", ".join(VALID_APP_ENVS)
            raise ValueError(f"APP_ENV must be one of: {allowed}")
        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in VALID_LOG_LEVELS:
            allowed = ", ".join(VALID_LOG_LEVELS)
            raise ValueError(f"LOG_LEVEL must be one of: {allowed}")
        return normalized

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_LOG_FORMATS:
            allowed = ", ".join(VALID_LOG_FORMATS)
            raise ValueError(f"LOG_FORMAT must be one of: {allowed}")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        validated: list[str] = []
        for origin in value:
            if origin == "*":
                validated.append(origin)
                continue
            parsed = urlparse(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Each CORS_ORIGINS entry must be '*' or an http(s) origin URL"
                )
            validated.append(f"{parsed.scheme}://{parsed.netloc}")
        return validated

    @field_validator("cors_allow_methods")
    @classmethod
    def validate_cors_allow_methods(cls, value: list[str]) -> list[str]:
        return [item.upper() for item in value]

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

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        parsed = urlparse(trimmed)
        if parsed.scheme not in {"redis", "rediss"}:
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        if not parsed.hostname:
            raise ValueError("REDIS_URL must include a hostname")
        return trimmed

    @field_validator("smtp_host", "smtp_username", mode="before")
    @classmethod
    def normalize_optional_str(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def validate_environment_consistency(self) -> "Settings":
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS cannot be true when CORS_ORIGINS contains '*'"
            )
        if self.app_env == "production":
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS cannot contain '*' in production")
            if self.jwt_secret_key.get_secret_value().startswith("replace-with-"):
                raise ValueError(
                    "JWT_SECRET_KEY must not use the example placeholder in production"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
