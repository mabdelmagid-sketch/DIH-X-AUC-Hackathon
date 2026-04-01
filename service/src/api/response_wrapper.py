"""
response_wrapper.py -- Loving Loyalty AI Suite

Implements the Loving Loyalty API standard response envelope.

Success responses:
    { "data": <payload>, "meta": { "version", "timestamp", "requestId" } }

Error responses:
    { "error": { "code", "message", "details", "timestamp", "requestId" } }

Usage::

    from .response_wrapper import wrap_response, wrap_error, APIResponse

    # In a route handler:
    return wrap_response(my_payload_dict, request_id="abc123")

    # For errors (raises HTTPException):
    raise wrap_error(400, "INVALID_INPUT", "endDate must be >= startDate")
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel

# Increment when the API contract changes
_API_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Pydantic models for the envelope
# ---------------------------------------------------------------------------

class ResponseMeta(BaseModel):
    version: str
    timestamp: str
    requestId: str


class APIResponse(BaseModel):
    """Standard success envelope."""
    data: Any
    meta: ResponseMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
    timestamp: str
    requestId: str


class APIErrorResponse(BaseModel):
    """Standard error envelope."""
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _new_request_id() -> str:
    return str(uuid.uuid4())


def wrap_response(
    payload: Any,
    *,
    request_id: Optional[str] = None,
    version: str = _API_VERSION,
) -> dict:
    """Wrap a payload in the standard Loving Loyalty success envelope.

    Args:
        payload: The response body (dict, list, Pydantic model, or primitive).
        request_id: Optional caller-supplied request ID for tracing.
                    A new UUID is generated if not provided.
        version: API version string to include in meta.

    Returns:
        Dict with ``data`` and ``meta`` keys suitable for returning from a
        FastAPI route.  FastAPI will serialize it as JSON.
    """
    if hasattr(payload, "model_dump"):
        # Pydantic v2
        data = payload.model_dump()
    elif hasattr(payload, "dict"):
        # Pydantic v1
        data = payload.dict()
    else:
        data = payload

    return {
        "data": data,
        "meta": {
            "version": version,
            "timestamp": _now_iso(),
            "requestId": request_id or _new_request_id(),
        },
    }


def wrap_error(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    *,
    request_id: Optional[str] = None,
) -> HTTPException:
    """Build an HTTPException whose detail is the standard error envelope.

    Raise the returned exception in route handlers::

        raise wrap_error(404, "PLACE_NOT_FOUND", "No sales data for placeId=42")

    Args:
        status_code: HTTP status code (400, 404, 422, 500, …).
        code: Machine-readable error code string (e.g. "INVALID_DATE_RANGE").
        message: Human-readable description.
        details: Optional extra context (validation errors, field names, …).
        request_id: Optional tracing ID.

    Returns:
        An HTTPException ready to be raised.
    """
    rid = request_id or _new_request_id()
    error_body = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "timestamp": _now_iso(),
            "requestId": rid,
        }
    }
    return HTTPException(status_code=status_code, detail=error_body)
