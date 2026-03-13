"""Logging configuration helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.core.config import AppSettings
from app.core.request_context import get_request_id


class RequestContextFilter(logging.Filter):
    """Inject request context into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(settings: AppSettings) -> None:
    """Configure application logging once per process."""

    root_logger = logging.getLogger()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    request_filter = RequestContextFilter()

    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s",
            )
        )
        handler.addFilter(request_filter)
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            if not any(isinstance(existing_filter, RequestContextFilter) for existing_filter in handler.filters):
                handler.addFilter(request_filter)

    root_logger.setLevel(level)


def format_log_fields(**fields: Any) -> str:
    """Render structured fields into a stable key=value suffix."""

    rendered: list[str] = []
    for key, value in sorted(fields.items()):
        if value is None:
            continue
        if isinstance(value, Mapping):
            value = dict(value)
        rendered.append(f"{key}={value}")
    return " ".join(rendered)


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    """Emit a structured log message with a stable key=value suffix."""

    suffix = format_log_fields(**fields)
    logger.log(level, f"{message}{' ' + suffix if suffix else ''}")
