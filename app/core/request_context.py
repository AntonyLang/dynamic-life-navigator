"""Request context propagation helpers."""

from __future__ import annotations

from contextvars import ContextVar

_request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    """Store the current request ID in context."""

    _request_id_context.set(request_id)


def clear_request_id() -> None:
    """Clear the current request ID from context."""

    _request_id_context.set(None)


def get_request_id() -> str | None:
    """Return the current request ID if one is set."""

    return _request_id_context.get()
