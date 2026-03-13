"""Event log compression helpers."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models.event_log import EventLog

logger = logging.getLogger(__name__)
settings = get_settings()
DEFAULT_COMPACTION_WINDOW = timedelta(days=1)


def compress_event_logs(
    db: Session,
    *,
    older_than: timedelta = DEFAULT_COMPACTION_WINDOW,
) -> dict[str, int | str]:
    """Mark old events as compressed and attach a lightweight summary."""

    now = datetime.now(timezone.utc)
    cutoff = now - older_than
    events = db.scalars(
        select(EventLog).where(
            EventLog.user_id == settings.default_user_id,
            EventLog.processed_status == "new",
            EventLog.occurred_at < cutoff,
        )
    ).all()

    if not events:
        log_event(
            logger,
            logging.INFO,
            "event compression completed",
            user_id=settings.default_user_id,
            compressed_count=0,
            cutoff=cutoff.isoformat(),
        )
        return {"status": "completed", "compressed_count": 0}

    source_counts = Counter(event.source for event in events)
    parse_counts = Counter(event.parse_status for event in events)

    for event in events:
        event.parsed_impact = {
            **(event.parsed_impact or {}),
            "compression_summary": {
                "compressed_at": now.isoformat(),
                "source": event.source,
                "parse_status": event.parse_status,
                "has_raw_text": bool(event.raw_text),
                "has_raw_payload": bool(event.raw_payload),
            },
        }
        event.processed_status = "compressed"
        db.add(event)

    db.commit()
    log_event(
        logger,
        logging.INFO,
        "event compression completed",
        user_id=settings.default_user_id,
        compressed_count=len(events),
        source_counts=dict(source_counts),
        parse_counts=dict(parse_counts),
    )
    return {"status": "completed", "compressed_count": len(events)}
