"""API errors. Every one renders as {"error": {"code": "snake_case", "message": "..."}}."""

from __future__ import annotations

from typing import Any

import httpx
from google.genai import errors as genai_errors

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
CUT_OFF_MESSAGE = "The model's reply was cut off at its length limit. Try again."


class ApiError(Exception):
    status = 500
    code = "internal_error"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status

    def body(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


class BadRequest(ApiError):
    status = 400
    code = "bad_request"


class DeviceRequired(ApiError):
    """No X-SIB-Device header, or one that is not a device key (API.md, "Callers and ownership")."""

    status = 401
    code = "device_required"


class NotFound(ApiError):
    status = 404
    code = "not_found"


class InvalidState(ApiError):
    status = 409
    code = "invalid_state"


class PayloadTooLarge(ApiError):
    status = 413
    code = "payload_too_large"


class UnsupportedMedia(ApiError):
    status = 415
    code = "unsupported_media_type"


class Unprocessable(ApiError):
    status = 422
    code = "validation_error"


class RateLimited(ApiError):
    status = 429
    code = "rate_limited"

    def __init__(self, message: str, *, code: str | None = None, retry_after: int | None = None):
        super().__init__(message, code=code)
        self.retry_after = retry_after


class UpstreamBusy(ApiError):
    """Gemini answered 429 or 5xx twice, or timed out."""

    status = 503
    code = "upstream_busy"


class UpstreamError(ApiError):
    """Gemini refused the request or returned something unusable."""

    status = 502
    code = "upstream_error"


def is_retryable(exc: BaseException) -> bool:
    """True for a Gemini 429/5xx, which the API reports as upstream_busy."""
    return isinstance(exc, genai_errors.APIError) and exc.code in RETRYABLE_STATUS


def as_upstream_error(exc: BaseException) -> ApiError:
    """Map a model-layer exception to the API's 503 upstream_busy or 502 upstream_error."""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, TimeoutError | httpx.TransportError) or is_retryable(exc):
        return UpstreamBusy("The model service is busy. Try again in a moment.")
    return UpstreamError("The model service could not complete the request.")


def quote(value: object, limit: int) -> str:
    """A submitted value as an error message may show it: at most `limit` characters, any that
    cannot be printed (a control character, a lone surrogate) replaced, in single quotes, with an
    ellipsis when it was cut. An error never echoes more of a request than that."""
    text = str(value)
    shown = "".join(c if c.isprintable() else "?" for c in text[:limit])
    return f"'{shown}{'…' if len(text) > limit else ''}'"


def safe_describe(exc: BaseException) -> str:
    """For logs: the exception type, plus the server's own reason for a Gemini API error.

    Never the message of other exceptions: a validation error can echo transcript text.
    """
    if isinstance(exc, genai_errors.APIError):
        return f"{type(exc).__name__}: {str(exc)[:600]}"
    return type(exc).__name__
