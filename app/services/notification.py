import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.constants import DEFAULT_SMTP_FROM_EMAIL, DEFAULT_SMTP_PORT

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TaskAssignmentNotification:
    task_id: int
    task_title: str
    project_id: int
    project_name: str
    assignee_id: int
    assignee_email: str
    assignee_name: str
    assigned_by_id: int
    assigned_by_name: str


class NotificationService:
    def __init__(
        self,
        *,
        smtp_host: str | None = None,
        smtp_port: int = DEFAULT_SMTP_PORT,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
        smtp_from_email: str = DEFAULT_SMTP_FROM_EMAIL,
        smtp_use_tls: bool = True,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_from_email = smtp_from_email
        self.smtp_use_tls = smtp_use_tls

    def build_assignment_email(
        self, notification: TaskAssignmentNotification
    ) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = f"[TaskHub] Task assigned: {notification.task_title}"
        message["From"] = self.smtp_from_email
        message["To"] = notification.assignee_email
        message.set_content(
            f"Hello {notification.assignee_name},\n\n"
            f"You have been assigned to task #{notification.task_id}: "
            f'"{notification.task_title}" in project '
            f'"{notification.project_name}" by {notification.assigned_by_name}.\n'
        )
        return message

    def _deliver_smtp(self, message: EmailMessage) -> None:
        assert self.smtp_host is not None
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5.0) as smtp:
            if self.smtp_use_tls:
                smtp.starttls()
            if self.smtp_username and self.smtp_password is not None:
                smtp.login(self.smtp_username, self.smtp_password)
            smtp.send_message(message)

    async def send_task_assigned_email(
        self, notification: TaskAssignmentNotification
    ) -> None:
        message = self.build_assignment_email(notification)
        if not self.smtp_host:
            logger.info(
                "Task #%s (%s) assigned to %s <%s> by %s",
                notification.task_id,
                notification.task_title,
                notification.assignee_name,
                notification.assignee_email,
                notification.assigned_by_name,
            )
            return

        try:
            await asyncio.to_thread(self._deliver_smtp, message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning(
                "Failed to send assignment email to %s for task %s: %s",
                notification.assignee_email,
                notification.task_id,
                exc,
            )
