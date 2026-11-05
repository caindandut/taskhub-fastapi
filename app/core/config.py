from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: SecretStr

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
