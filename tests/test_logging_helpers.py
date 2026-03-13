import logging

from app.core.logging import format_log_fields, log_event


def test_format_log_fields_sorts_keys_and_skips_none():
    rendered = format_log_fields(beta=2, alpha=1, omit=None)

    assert rendered == "alpha=1 beta=2"


def test_log_event_emits_structured_suffix(caplog):
    logger = logging.getLogger("tests.logging")

    with caplog.at_level(logging.INFO, logger="tests.logging"):
        log_event(logger, logging.INFO, "structured message", event_id="evt-1", status="ok")

    assert "structured message event_id=evt-1 status=ok" in caplog.text
