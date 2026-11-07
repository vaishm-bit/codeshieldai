"""Errors raised by the AI layer. They map to clean HTTP responses via AppError."""

from app.core.exceptions import AppError


class AINotConfiguredError(AppError):
    status_code = 503
    code = "ai_not_configured"


class AIRateLimitError(AppError):
    status_code = 429
    code = "ai_rate_limited"

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        details = {"retry_after_seconds": retry_after} if retry_after is not None else None
        super().__init__(message, details)
        self.retry_after = retry_after


class AIProviderError(AppError):
    status_code = 502
    code = "ai_provider_error"


class AIResponseError(AppError):
    status_code = 502
    code = "ai_invalid_response"
