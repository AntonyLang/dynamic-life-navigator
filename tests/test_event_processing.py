from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.services.event_processing import apply_state_patch_from_event, parse_event_log

settings = get_settings()


def test_parse_and_apply_state_patch_updates_snapshot():
    event_id = uuid4()

    with SessionLocal() as session:
        created_state = False
        state = session.get(UserState, settings.default_user_id)
        if state is None:
            state = UserState(user_id=settings.default_user_id, mental_energy=60, physical_energy=70, focus_mode="unknown")
            session.add(state)
            session.commit()
            session.refresh(state)
            created_state = True

        original_version = state.state_version
        original_mental = state.mental_energy
        original_physical = state.physical_energy
        original_focus = state.focus_mode
        original_recent_context = state.recent_context
        original_updated_at = state.updated_at
        original_event_id = state.source_last_event_id
        original_event_at = state.source_last_event_at

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
            assert refreshed_event.parse_status == "fallback"
            assert snapshot.focus_mode == "tired"
            assert refreshed_state.state_version == original_version + 1
            assert refreshed_state.mental_energy <= original_mental
            assert refreshed_state.physical_energy == original_physical
            assert history is not None
        finally:
            session.execute(delete(StateHistory).where(StateHistory.event_id == event_id))
            session.execute(delete(EventLog).where(EventLog.event_id == event_id))
            if created_state:
                session.execute(delete(UserState).where(UserState.user_id == settings.default_user_id))
            else:
                restored_state = session.get(UserState, settings.default_user_id)
                restored_state.state_version = original_version
                restored_state.mental_energy = original_mental
                restored_state.physical_energy = original_physical
                restored_state.focus_mode = original_focus
                restored_state.recent_context = original_recent_context
                restored_state.updated_at = original_updated_at
                restored_state.source_last_event_id = original_event_id
                restored_state.source_last_event_at = original_event_at
                session.add(restored_state)
            session.commit()
