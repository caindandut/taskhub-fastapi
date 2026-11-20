import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.constants import (
    INTERNAL_SERVER_ERROR,
    PROCESS_TIME_HEADER,
    REQUEST_ID_HEADER,
)
from app.core.logging import (
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    configure_logging,
    get_request_id,
)
from app.main import app, create_app
from tests.conftest import TEST_JWT_SECRET


def _base_settings_kwargs(database_url: str) -> dict[str, object]:
    return {
        "database_url": database_url,
        "jwt_secret_key": TEST_JWT_SECRET,
        "_env_file": None,
    }


def test_settings_defaults_and_normalization(database_url: str) -> None:
    settings = Settings(**_base_settings_kwargs(database_url))

    assert settings.app_name == "TaskHub API"
    assert settings.app_version == "0.1.0"
    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert settings.cors_allow_credentials is True

    custom = Settings(
        **_base_settings_kwargs(database_url),
        app_env=" Staging ",
        log_level="debug",
        log_format="TEXT",
        cors_origins="http://localhost:5173/, https://app.example.com",
        cors_allow_methods="get, post",
        cors_allow_headers="Authorization, Content-Type",
    )
    assert custom.app_env == "staging"
    assert custom.log_level == "DEBUG"
    assert custom.log_format == "text"
    assert custom.cors_origins == ["http://localhost:5173", "https://app.example.com"]
    assert custom.cors_allow_methods == ["GET", "POST"]
    assert custom.cors_allow_headers == ["Authorization", "Content-Type"]


def test_settings_json_cors_and_empty_cors(database_url: str) -> None:
    json_settings = Settings(
        **_base_settings_kwargs(database_url),
        cors_origins='["https://a.example.com", "http://b.example.com:8080/"]',
    )
    assert json_settings.cors_origins == [
        "https://a.example.com",
        "http://b.example.com:8080",
    ]

    empty_settings = Settings(**_base_settings_kwargs(database_url), cors_origins="")
    assert empty_settings.cors_origins == []


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"app_name": "   "},
        {"app_env": "prod"},
        {"log_level": "TRACE"},
        {"log_format": "xml"},
        {"cors_origins": "localhost:3000"},
        {"cors_origins": "ftp://example.com"},
        {"cors_origins": "https://example.com/api"},
        {"cors_origins": "[not-valid-json"},
        {"cors_origins": "*", "cors_allow_credentials": True},
        {
            "app_env": "production",
            "cors_origins": "*",
            "cors_allow_credentials": False,
        },
        {
            "app_env": "production",
            "jwt_secret_key": "replace-with-a-random-secret-key-at-least-32-characters",
        },
    ],
)
def test_settings_reject_invalid_env_configuration(
    database_url: str, bad_kwargs: dict[str, object]
) -> None:
    kwargs = _base_settings_kwargs(database_url) | bad_kwargs
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_wildcard_cors_allowed_in_non_production_without_credentials(
    database_url: str,
) -> None:
    settings = Settings(
        **_base_settings_kwargs(database_url),
        app_env="development",
        cors_origins="*",
        cors_allow_credentials=False,
    )
    assert settings.cors_origins == ["*"]


def test_request_id_and_process_time_headers(database_url: str) -> None:
    with TestClient(app) as client:
        auto_res = client.get("/api/v1/health")
        assert auto_res.status_code == 200
        generated_id = auto_res.headers[REQUEST_ID_HEADER]
        assert len(generated_id) == 32
        assert float(auto_res.headers[PROCESS_TIME_HEADER]) >= 0.0

        supplied_id = "req-client_01.trace"
        echo_res = client.get(
            "/api/v1/health", headers={REQUEST_ID_HEADER: supplied_id}
        )
        assert echo_res.status_code == 200
        assert echo_res.headers[REQUEST_ID_HEADER] == supplied_id
        assert float(echo_res.headers[PROCESS_TIME_HEADER]) >= 0.0

        # Invalid characters or overly long IDs must be replaced with a safe ID.
        unsafe_res = client.get(
            "/api/v1/health", headers={REQUEST_ID_HEADER: "bad id with spaces!"}
        )
        assert unsafe_res.headers[REQUEST_ID_HEADER] != "bad id with spaces!"
        assert len(unsafe_res.headers[REQUEST_ID_HEADER]) == 32

        too_long = "a" * 200
        long_res = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: too_long})
        assert long_res.headers[REQUEST_ID_HEADER] != too_long
        assert len(long_res.headers[REQUEST_ID_HEADER]) == 32

    assert get_request_id() is None


def test_cors_headers_and_preflight(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://frontend.example.com")
    get_settings.cache_clear()

    with TestClient(app) as client:
        preflight = client.options(
            "/api/v1/health",
            headers={
                "Origin": "https://frontend.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization, X-Request-ID",
            },
        )
        assert preflight.status_code == 200
        assert (
            preflight.headers["Access-Control-Allow-Origin"]
            == "https://frontend.example.com"
        )
        assert preflight.headers["Access-Control-Allow-Credentials"] == "true"
        assert REQUEST_ID_HEADER in preflight.headers
        assert PROCESS_TIME_HEADER in preflight.headers

        allowed = client.get(
            "/api/v1/health",
            headers={"Origin": "https://frontend.example.com"},
        )
        assert allowed.status_code == 200
        assert (
            allowed.headers["Access-Control-Allow-Origin"]
            == "https://frontend.example.com"
        )
        exposed = allowed.headers.get("Access-Control-Expose-Headers", "")
        assert REQUEST_ID_HEADER in exposed
        assert PROCESS_TIME_HEADER in exposed

        disallowed = client.get(
            "/api/v1/health",
            headers={"Origin": "https://evil.example.com"},
        )
        assert disallowed.status_code == 200
        assert "Access-Control-Allow-Origin" not in disallowed.headers


def test_logging_formatters_and_idempotent_configuration() -> None:
    json_formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Task %s created",
        args=(42,),
        exc_info=None,
    )
    record.request_id = "req-123"
    record.method = "POST"
    record.path = "/api/v1/tasks"
    record.status_code = 201
    record.duration_ms = 12.5

    parsed = json.loads(json_formatter.format(record))
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "app.test"
    assert parsed["message"] == "Task 42 created"
    assert parsed["request_id"] == "req-123"
    assert parsed["method"] == "POST"
    assert parsed["path"] == "/api/v1/tasks"
    assert parsed["status_code"] == 201
    assert parsed["duration_ms"] == 12.5
    assert "timestamp" in parsed

    text_formatter = TextFormatter()
    text_line = text_formatter.format(record)
    assert "INFO" in text_line
    assert "[req-123]" in text_line
    assert "Task 42 created" in text_line

    # Verify configure_logging is idempotent and does not duplicate its handler.
    root = logging.getLogger()
    previous_level = root.level
    try:
        configure_logging(log_level="DEBUG", log_format="json")
        count_first = sum(
            1 for h in root.handlers if getattr(h, "_taskhub_handler", False)
        )
        configure_logging(log_level="INFO", log_format="text")
        count_second = sum(
            1 for h in root.handlers if getattr(h, "_taskhub_handler", False)
        )
        assert count_first == 1
        assert count_second == 1
    finally:
        root.setLevel(previous_level)


def test_access_logging_and_request_id_correlation(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    req_id = "trace-access-001"
    with caplog.at_level(logging.INFO), TestClient(app) as client:
        res = client.get("/api/v1/health", headers={REQUEST_ID_HEADER: req_id})

    assert res.status_code == 200
    access_records = [
        rec
        for rec in caplog.records
        if rec.name == "app.access" and "/api/v1/health" in rec.getMessage()
    ]
    assert len(access_records) == 1
    rec = access_records[0]
    assert rec.request_id == req_id  # type: ignore[attr-defined]
    assert rec.status_code == 200  # type: ignore[attr-defined]
    assert rec.method == "GET"  # type: ignore[attr-defined]
    assert get_request_id() is None


def test_validation_error_is_sanitized_and_includes_request_id(
    database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    secret_password = "pw-1"
    with caplog.at_level(logging.WARNING), TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/register",
            headers={REQUEST_ID_HEADER: "val-err-422"},
            json={
                "email": "user@example.com",
                "full_name": "Tester",
                "password": secret_password,
            },
        )

    assert res.status_code == 422
    assert res.headers[REQUEST_ID_HEADER] == "val-err-422"
    body = res.json()
    assert isinstance(body["detail"], list)
    assert len(body["detail"]) >= 1
    assert "loc" in body["detail"][0]
    assert "msg" in body["detail"][0]
    assert "type" in body["detail"][0]
    # Ensure raw submitted secret input is never echoed back in validation errors.
    assert "input" not in body["detail"][0]
    assert secret_password not in res.text


def test_unhandled_exception_returns_sanitized_500_with_request_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'infra_500.db').as_posix()}"
    settings = Settings(
        database_url=db_url,
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="INFO",
        log_format="json",
        _env_file=None,
    )
    probe_app = create_app(settings=settings)

    @probe_app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("sensitive internal db connection string")

    with (
        caplog.at_level(logging.ERROR),
        TestClient(probe_app, raise_server_exceptions=False) as client,
    ):
        res = client.get(
            "/api/v1/boom",
            headers={REQUEST_ID_HEADER: "boom-trace-500"},
        )

    assert res.status_code == 500
    assert res.json() == {"detail": INTERNAL_SERVER_ERROR}
    assert res.headers[REQUEST_ID_HEADER] == "boom-trace-500"
    assert "sensitive internal db connection string" not in res.text

    error_logs = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert len(error_logs) == 1
    assert error_logs[0].request_id == "boom-trace-500"  # type: ignore[attr-defined]


def test_request_id_filter_populates_record_from_context() -> None:
    log_filter = RequestIdFilter()
    record = logging.LogRecord("app.filter", logging.INFO, __file__, 1, "hi", (), None)
    assert log_filter.filter(record) is True
    assert record.request_id is None  # type: ignore[attr-defined]
