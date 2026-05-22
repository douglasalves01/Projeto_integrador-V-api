"""Application-specific exceptions."""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""

    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class UserNotFoundError(AppError):
    status_code = 404

    def __init__(self, user_id: int | str) -> None:
        self.user_id = int(user_id)
        super().__init__(f"User {self.user_id} not found")


class ResourceNotFoundError(AppError):
    status_code = 404

    def __init__(self, resource: str, identifier: int | str) -> None:
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} {identifier} not found")


class DatabaseTimeoutError(AppError):
    status_code = 504

    def __init__(self) -> None:
        super().__init__("Database operation timed out")
