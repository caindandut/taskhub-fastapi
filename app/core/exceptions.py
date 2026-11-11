from fastapi import status

from app.core.messages import TASK_NOT_FOUND


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AppException):
    """Resource not found exception."""

    def __init__(self, message: str = TASK_NOT_FOUND) -> None:
        super().__init__(message=message, status_code=status.HTTP_404_NOT_FOUND)
