from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def not_found(resource: str, resource_id: object) -> AppError:
    return AppError(
        f"{resource.upper()}_NOT_FOUND",
        f"{resource} 不存在",
        status_code=404,
        details={"id": str(resource_id)},
    )
