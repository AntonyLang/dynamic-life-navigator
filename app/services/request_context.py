"""Helpers for API/service boundary request metadata."""

from __future__ import annotations

from fastapi import Request


def get_request_id_from_request(request: Request) -> str:
    """Extract the request ID assigned by middleware."""

    return getattr(request.state, "request_id", "unknown-request")
