"""
CULTURA — JSON response helpers.

Standardizes successful and error responses for API endpoints so that
all consumers (frontend fetch, future mobile apps, etc.) receive a
consistent contract.

Design principles:
- Every JSON response is a dict with a predictable shape.
- Success responses include `ok: true` and a `data` payload.
- Error responses include `ok: false`, an `error` object with `code`,
  `message`, and optional `details`.
- HTTP status codes are used correctly (2xx for success, 4xx for client
  errors, 5xx for server errors).
- No internal tracebacks or sensitive details leak to the client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from flask import jsonify, Response


@dataclass(frozen=True)
class APIError:
    """Structured error payload for API responses."""
    code: str
    message: str
    details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            result["details"] = self.details
        return result


# ---------------------------------------------------------------------------
# Predefined error codes
# ---------------------------------------------------------------------------

class ErrorCodes:
    """Canonical error codes used across the API."""

    # 400 Bad Request
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_JSON = "INVALID_JSON"
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FIELD_VALUE = "INVALID_FIELD_VALUE"

    # 401 Unauthorized
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"

    # 403 Forbidden
    FORBIDDEN = "FORBIDDEN"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    ADMIN_REQUIRED = "ADMIN_REQUIRED"

    # 404 Not Found
    NOT_FOUND = "NOT_FOUND"
    EVENT_NOT_FOUND = "EVENT_NOT_FOUND"
    COMPETITION_NOT_FOUND = "COMPETITION_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    TEAM_NOT_FOUND = "TEAM_NOT_FOUND"
    REGISTRATION_NOT_FOUND = "REGISTRATION_NOT_FOUND"

    # 409 Conflict
    CONFLICT = "CONFLICT"
    DUPLICATE_REGISTRATION = "DUPLICATE_REGISTRATION"
    DUPLICATE_TEAM_MEMBER = "DUPLICATE_TEAM_MEMBER"
    DUPLICATE_EMAIL = "DUPLICATE_EMAIL"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    DEADLINE_PASSED = "DEADLINE_PASSED"

    # 422 Unprocessable Entity
    UNPROCESSABLE = "UNPROCESSABLE"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"

    # 429 Too Many Requests
    RATE_LIMITED = "RATE_LIMITED"

    # 500 Internal Server Error
    INTERNAL_ERROR = "INTERNAL_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def success(data: Any = None, *, status: int = 200, message: Optional[str] = None) -> Response:
    """
    Build a successful JSON response.

    Args:
        data: The payload to return (any JSON-serializable value).
        status: HTTP status code (default 200).
        message: Optional human-readable success message.

    Returns:
        A Flask Response with JSON content.
    """
    payload: dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    resp = jsonify(payload)
    resp.status_code = status
    return resp


def created(data: Any = None, *, message: Optional[str] = None) -> Response:
    """Convenience wrapper for 201 Created."""
    return success(data, status=201, message=message)


def no_content(*, message: Optional[str] = None) -> Response:
    """Convenience wrapper for 204 No Content."""
    payload: dict[str, Any] = {"ok": True}
    if message is not None:
        payload["message"] = message
    resp = jsonify(payload)
    resp.status_code = 204
    return resp


def error(
    code: str,
    message: str,
    *,
    status: int = 400,
    details: Optional[dict[str, Any]] = None,
) -> Response:
    """
    Build an error JSON response.

    Args:
        code: Machine-readable error code (see ErrorCodes).
        message: Human-readable error message.
        status: HTTP status code (default 400).
        details: Optional additional structured details.

    Returns:
        A Flask Response with JSON content.
    """
    payload = {"ok": False, "error": APIError(code, message, details).to_dict()}
    resp = jsonify(payload)
    resp.status_code = status
    return resp


# ---------------------------------------------------------------------------
# Common error shortcuts
# ---------------------------------------------------------------------------

def bad_request(message: str, *, details: Optional[dict[str, Any]] = None) -> Response:
    """400 Bad Request."""
    return error(ErrorCodes.VALIDATION_ERROR, message, status=400, details=details)


def unauthorized(message: str = "Authentication required", *, code: str = ErrorCodes.UNAUTHENTICATED) -> Response:
    """401 Unauthorized."""
    return error(code, message, status=401)


def forbidden(message: str = "You do not have permission to perform this action") -> Response:
    """403 Forbidden."""
    return error(ErrorCodes.FORBIDDEN, message, status=403)


def not_found(resource: str = "Resource") -> Response:
    """404 Not Found."""
    return error(ErrorCodes.NOT_FOUND, f"{resource} not found", status=404)


def conflict(message: str, *, code: str = ErrorCodes.CONFLICT, details: Optional[dict[str, Any]] = None) -> Response:
    """409 Conflict."""
    return error(code, message, status=409, details=details)


def unprocessable(message: str, *, details: Optional[dict[str, Any]] = None) -> Response:
    """422 Unprocessable Entity."""
    return error(ErrorCodes.UNPROCESSABLE, message, status=422, details=details)


def rate_limited(retry_after: int) -> Response:
    """429 Too Many Requests."""
    resp = error(ErrorCodes.RATE_LIMITED, "Too many requests", status=429, details={"retry_after": retry_after})
    resp.headers["Retry-After"] = str(retry_after)
    return resp


def internal_error(message: str = "An unexpected error occurred") -> Response:
    """500 Internal Server Error."""
    return error(ErrorCodes.INTERNAL_ERROR, message, status=500)


def storage_error(message: str) -> Response:
    """500 Internal Server Error for storage failures."""
    return error(ErrorCodes.STORAGE_ERROR, message, status=500)


# ---------------------------------------------------------------------------
# Validation error helper
# ---------------------------------------------------------------------------

def validation_error(errors: dict[str, str]) -> Response:
    """
    Build a 400 response for form/JSON validation failures.

    Args:
        errors: Mapping of field name -> error message.

    Returns:
        A Flask Response with JSON content.
    """
    return bad_request(
        "Validation failed",
        details={"fields": errors},
    )


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------

def paginated(
    items: list[Any],
    *,
    page: int,
    per_page: int,
    total: int,
    message: Optional[str] = None,
) -> Response:
    """
    Build a paginated success response.

    Args:
        items: List of items for the current page.
        page: Current page number (1-indexed).
        per_page: Items per page.
        total: Total number of items across all pages.
        message: Optional message.

    Returns:
        A Flask Response with JSON content.
    """
    total_pages = (total + per_page - 1) // per_page if per_page else 1
    data = {
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }
    return success(data, message=message)