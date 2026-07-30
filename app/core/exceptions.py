"""Custom exceptions mapped to specific HTTP status codes and error codes.

Keeping these as distinct classes (rather than raising HTTPException directly
from deep in the service layer) lets route handlers stay thin and lets the
global exception handler produce one consistent error envelope everywhere.
"""


class AppError(Exception):
    """Base class for all handled application errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PayloadTooLargeError(AppError):
    status_code = 413
    error_code = "PAYLOAD_TOO_LARGE"


class RateLimitError(AppError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"


class ProviderBadResponseError(AppError):
    """OpenAI returned output that could not be turned into a valid response,
    even after one corrective retry."""

    status_code = 502
    error_code = "PROVIDER_BAD_RESPONSE"


class ProviderTimeoutError(AppError):
    status_code = 504
    error_code = "PROVIDER_TIMEOUT"


class ProviderConnectionError(AppError):
    """Network-level failure talking to OpenAI that isn't a timeout."""

    status_code = 502
    error_code = "PROVIDER_CONNECTION_ERROR"
