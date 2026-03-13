from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event_log import EventLog
from app.services.event_compaction_service import compress_event_logs

settings = get_settings()


def test_compress_event_logs_marks_old_events_as_compressed():
    old_event_id = uuid4()

    with SessionLocal() as session:
        session.add(
            EventLog(
                event_id=old_event_id,
                user_id=settings.default_user_id,
                source="desktop_plugin",
                source_event_type="text",
                external_event_id=f"compact-{old_event_id}",
                payload_hash=f"compact-{old_event_id}",
                raw_text="Old event to compress",
                raw_payload={"text": "Old event to compress"},
                parsed_impact={"event_type": "other"},
                parse_status="fallback",
                processed_status="new",
                occurred_at=datetime.now(timezone.utc) - timedelta(days=2),
                ingested_at=datetime.now(timezone.utc) - timedelta(days=2),
            )
        )
        session.commit()

        try:
            result = compress_event_logs(session)
            assert result["status"] == "completed"
            assert result["compressed_count"] >= 1

            refreshed = session.get(EventLog, old_event_id)
            assert refreshed.processed_status == "compressed"
            assert "compression_summary" in refreshed.parsed_impact
            assert refreshed.parsed_impact["compression_summary"]["parse_status"] == "fallback"
        finally:
            session.execute(delete(EventLog).where(EventLog.event_id == old_event_id))
            session.commit()


def test_compress_event_logs_leaves_recent_events_uncompressed():
    recent_event_id = uuid4()

    with SessionLocal() as session:
        session.add(
            EventLog(
                event_id=recent_event_id,
                user_id=settings.default_user_id,
                source="desktop_plugin",
                source_event_type="text",
                external_event_id=f"recent-{recent_event_id}",
                payload_hash=f"recent-{recent_event_id}",
                raw_text="Recent event should stay new",
                raw_payload={"text": "Recent event should stay new"},
                processed_status="new",
                occurred_at=datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        try:
            result = compress_event_logs(session)
            assert result["status"] == "completed"

            refreshed = session.get(EventLog, recent_event_id)
            assert refreshed.processed_status == "new"
            assert "compression_summary" not in refreshed.parsed_impact
        finally:
            session.execute(delete(EventLog).where(EventLog.event_id == recent_event_id))
            session.commit()
