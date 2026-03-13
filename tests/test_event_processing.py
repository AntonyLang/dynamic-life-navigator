from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.services import event_processing
from app.services.event_processing import apply_state_patch_from_event, parse_event_log

settings = get_settings()


def test_parse_and_apply_state_patch_updates_snapshot(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        original_state = user_state_guard
        original_version = original_state["state_version"]
        original_mental = original_state["mental_energy"]
        original_physical = original_state["physical_energy"]

        event = EventLog(
            event_id=event_id,
            user_id=settings.default_user_id,
            source="desktop_plugin",
            source_event_type="text",
            external_event_id=f"test-{event_id}",
            payload_hash=str(event_id),
            raw_text="I am drained after debugging all afternoon.",
            raw_payload={"text": "I am drained after debugging all afternoon."},
            occurred_at=datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
        )
        session.add(event)
        session.commit()

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)

            refreshed_event = session.get(EventLog, event_id)
            refreshed_state = session.get(UserState, settings.default_user_id)
            history = session.scalar(
                select(StateHistory)
                .where(StateHistory.event_id == event_id)
                .order_by(StateHistory.created_at.desc())
                .limit(1)
            )

            assert impact["event_type"] == "chat_update"
            assert impact["mental_delta"] < 0
            assert refreshed_event.parse_status == "success"
            assert snapshot.focus_mode == "tired"
            assert refreshed_state.state_version == original_version + 1
            assert refreshed_state.mental_energy <= original_mental
            assert refreshed_state.physical_energy == original_physical
            assert history is not None
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_failed_parse_keeps_event_and_skips_state_mutation(cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        original_state = user_state_guard

        session.add(
            EventLog(
                event_id=event_id,
                user_id=settings.default_user_id,
                source="desktop_plugin",
                source_event_type="text",
                external_event_id=f"failed-{event_id}",
                payload_hash=f"failed-{event_id}",
                raw_text=None,
                raw_payload=None,
                occurred_at=datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        try:
            impact = parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            refreshed_event = session.get(EventLog, event_id)
            refreshed_state = session.get(UserState, settings.default_user_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))

            assert impact == {}
            assert refreshed_event.parse_status == "failed"
            assert snapshot.mental_energy == original_state["mental_energy"]
            assert refreshed_state.state_version == original_state["state_version"]
            assert history is None
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_apply_state_patch_retries_on_compare_and_swap_conflict(monkeypatch, cleanup_db_artifacts, user_state_guard):
    event_id = uuid4()

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        original_state = user_state_guard

        session.add(
            EventLog(
                event_id=event_id,
                user_id=settings.default_user_id,
                source="desktop_plugin",
                source_event_type="text",
                external_event_id=f"cas-{event_id}",
                payload_hash=f"cas-{event_id}",
                raw_text="I feel tired after coding.",
                raw_payload={"text": "I feel tired after coding."},
                occurred_at=datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        parse_event_log(session, event_id)

        original_execute = session.execute
        call_count = {"updates": 0}

        class DummyResult:
            rowcount = 0

        def execute_once_conflicted(statement, *args, **kwargs):
            if getattr(statement, "table", None) is not None and statement.table.name == "user_state":
                call_count["updates"] += 1
                if call_count["updates"] == 1:
                    return DummyResult()
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(session, "execute", execute_once_conflicted)

        try:
            snapshot = apply_state_patch_from_event(session, event_id, max_retries=3)
            refreshed_state = session.get(UserState, settings.default_user_id)
            history = session.scalar(select(StateHistory).where(StateHistory.event_id == event_id))

            assert call_count["updates"] >= 2
            assert snapshot.focus_mode == "tired"
            assert refreshed_state.state_version == original_state["state_version"] + 1
            assert history is not None
        finally:
            cleanup_db_artifacts.event_ids(event_id)
