"""Logging configuration helpers."""

from __future__ import annotations

import logging

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
