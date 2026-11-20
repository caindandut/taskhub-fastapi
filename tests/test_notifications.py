import asyncio
import logging
import smtplib
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import get_notification_service
from app.core.security import create_access_token
from app.main import app
from app.services.notification import NotificationService, TaskAssignmentNotification
from tests.conftest import TEST_JWT_SECRET


def auth_headers(user_id: int = 1) -> dict[str, str]:
    token = create_access_token(subject=user_id, secret_key=TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


class RecordingNotificationService(NotificationService):
    def __init__(self) -> None:
        super().__init__(smtp_host=None)
        self.sent: list[TaskAssignmentNotification] = []

    async def send_task_assigned_email(
        self, notification: TaskAssignmentNotification
    ) -> None:
        self.sent.append(notification)
        await super().send_task_assigned_email(notification)


@pytest.fixture
def recorder(database_url: str) -> Iterator[RecordingNotificationService]:
    service = RecordingNotificationService()
    app.dependency_overrides[get_notification_service] = lambda: service
    try:
        yield service
    finally:
        app.dependency_overrides.pop(get_notification_service, None)


@pytest.fixture
def client(recorder: RecordingNotificationService) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        # Add user 2 (member@example.com) to workspace 1 as EDITOR
        res = test_client.post(
            "/api/v1/workspaces/1/members",
            headers=auth_headers(1),
            json={"user_id": 2, "role": "EDITOR"},
        )
        assert res.status_code == 201
        yield test_client


def test_create_task_triggers_notification_only_when_assigned(
    client: TestClient, recorder: RecordingNotificationService
) -> None:
    # Unassigned task -> no notification
    unassigned = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Unassigned task"},
    )
    assert unassigned.status_code == 201
    assert recorder.sent == []

    # Assigned task via /projects/{id}/tasks -> triggers notification
    assigned = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Implement notifications", "assignee_id": 2},
    )
    assert assigned.status_code == 201
    task_id = assigned.json()["id"]
    assert len(recorder.sent) == 1
    assert recorder.sent[0] == TaskAssignmentNotification(
        task_id=task_id,
        task_title="Implement notifications",
        project_id=1,
        project_name="Backend",
        assignee_id=2,
        assignee_email="member@example.com",
        assignee_name="Member",
        assigned_by_id=1,
        assigned_by_name="Owner",
    )

    # Assigned task via /tasks -> triggers notification
    recorder.sent.clear()
    flat_assigned = client.post(
        "/api/v1/tasks",
        headers=auth_headers(2),
        json={"title": "Flat assigned task", "project_id": 1, "assignee_id": 1},
    )
    assert flat_assigned.status_code == 201
    assert len(recorder.sent) == 1
    assert recorder.sent[0].assignee_id == 1
    assert recorder.sent[0].assignee_email == "owner@example.com"
    assert recorder.sent[0].assigned_by_id == 2
    assert recorder.sent[0].assigned_by_name == "Member"


def test_update_task_notification_conditions(
    client: TestClient, recorder: RecordingNotificationService
) -> None:
    task = client.post(
        "/api/v1/projects/1/tasks",
        headers=auth_headers(1),
        json={"title": "Initial unassigned"},
    ).json()
    task_id = task["id"]
    assert recorder.sent == []

    # 1. Assign user 2 -> triggers notification
    r1 = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(1),
        json={"assignee_id": 2},
    )
    assert r1.status_code == 200
    assert len(recorder.sent) == 1
    assert recorder.sent[0].assignee_id == 2

    # 2. Patch with SAME assignee_id=2 -> does NOT trigger duplicate notification
    recorder.sent.clear()
    r_same = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(1),
        json={"assignee_id": 2, "title": "Renamed"},
    )
    assert r_same.status_code == 200
    assert recorder.sent == []

    # 3. Patch status only (assignee_id not in payload) -> does NOT trigger notification
    r_status = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(1),
        json={"status": "IN_PROGRESS"},
    )
    assert r_status.status_code == 200
    assert recorder.sent == []

    # 4. Reassign to user 1 -> triggers notification for user 1
    r_reassign = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(2),
        json={"assignee_id": 1},
    )
    assert r_reassign.status_code == 200
    assert len(recorder.sent) == 1
    assert recorder.sent[0].assignee_id == 1
    assert recorder.sent[0].assignee_email == "owner@example.com"
    assert recorder.sent[0].task_title == "Renamed"

    # 5. Clear assignee (assignee_id=None) -> does NOT trigger notification
    recorder.sent.clear()
    r_clear = client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=auth_headers(1),
        json={"assignee_id": None},
    )
    assert r_clear.status_code == 200
    assert recorder.sent == []


def test_notification_service_smtp_delivery_and_error_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    notification = TaskAssignmentNotification(
        task_id=10,
        task_title="Deploy Redis",
        project_id=1,
        project_name="Backend",
        assignee_id=2,
        assignee_email="member@example.com",
        assignee_name="Member",
        assigned_by_id=1,
        assigned_by_name="Owner",
    )

    # 1. Logging fallback when smtp_host is None
    fallback_service = NotificationService(smtp_host=None)
    with caplog.at_level(logging.INFO):
        asyncio.run(fallback_service.send_task_assigned_email(notification))
    assert (
        "Task #10 (Deploy Redis) assigned to Member <member@example.com>" in caplog.text
    )

    # 2. Successful SMTP delivery with TLS and login
    mock_smtp_instance = MagicMock()
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp_instance
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_cls)

    smtp_service = NotificationService(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="mailer",
        smtp_password="secret",
        smtp_from_email="alerts@example.com",
        smtp_use_tls=True,
    )
    asyncio.run(smtp_service.send_task_assigned_email(notification))

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=5.0)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("mailer", "secret")
    mock_smtp_instance.send_message.assert_called_once()
    sent_msg = mock_smtp_instance.send_message.call_args[0][0]
    assert sent_msg["Subject"] == "[TaskHub] Task assigned: Deploy Redis"
    assert sent_msg["From"] == "alerts@example.com"
    assert sent_msg["To"] == "member@example.com"
    assert 'task #10: "Deploy Redis"' in sent_msg.get_content()

    # 3. SMTP failure logs warning and does not raise exception
    mock_smtp_instance.send_message.side_effect = smtplib.SMTPException("SMTP down")
    with caplog.at_level(logging.WARNING):
        asyncio.run(smtp_service.send_task_assigned_email(notification))
    assert "Failed to send assignment email to member@example.com" in caplog.text


def test_smtp_failure_in_background_does_not_fail_api_request(
    database_url: str,
) -> None:
    failing_service = NotificationService(smtp_host="127.0.0.1", smtp_port=9)
    failing_service._deliver_smtp = MagicMock(side_effect=OSError("Connection refused"))
    app.dependency_overrides[get_notification_service] = lambda: failing_service
    try:
        with TestClient(app, headers=auth_headers(1)) as client:
            res = client.post(
                "/api/v1/projects/1/tasks",
                json={"title": "Resilient task", "assignee_id": 1},
            )
            assert res.status_code == 201
            assert res.json()["assignee_id"] == 1
    finally:
        app.dependency_overrides.pop(get_notification_service, None)


def test_smtp_settings_normalization(database_url: str) -> None:
    settings = Settings(
        database_url=database_url,
        jwt_secret_key=TEST_JWT_SECRET,
        smtp_host="   ",
        smtp_username="  user@example.com  ",
    )
    assert settings.smtp_host is None
    assert settings.smtp_username == "user@example.com"
