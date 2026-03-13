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
            assert refreshed_event.parse_status == "success"
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


def test_failed_parse_keeps_event_and_skips_state_mutation():
    event_id = uuid4()

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        if state is None:
            state = UserState(user_id=settings.default_user_id)
            session.add(state)
            session.commit()
            session.refresh(state)

        original_state = {
            "mental_energy": state.mental_energy,
            "physical_energy": state.physical_energy,
            "focus_mode": state.focus_mode,
            "state_version": state.state_version,
            "recent_context": state.recent_context,
            "updated_at": state.updated_at,
            "source_last_event_id": state.source_last_event_id,
            "source_last_event_at": state.source_last_event_at,
        }

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
            session.execute(delete(EventLog).where(EventLog.event_id == event_id))
            restored_state = session.get(UserState, settings.default_user_id)
            restored_state.mental_energy = original_state["mental_energy"]
            restored_state.physical_energy = original_state["physical_energy"]
            restored_state.focus_mode = original_state["focus_mode"]
            restored_state.state_version = original_state["state_version"]
            restored_state.recent_context = original_state["recent_context"]
            restored_state.updated_at = original_state["updated_at"]
            restored_state.source_last_event_id = original_state["source_last_event_id"]
            restored_state.source_last_event_at = original_state["source_last_event_at"]
            session.add(restored_state)
            session.commit()


def test_apply_state_patch_retries_on_compare_and_swap_conflict(monkeypatch):
    event_id = uuid4()

    with SessionLocal() as session:
        state = session.get(UserState, settings.default_user_id)
        if state is None:
            state = UserState(user_id=settings.default_user_id, mental_energy=60, physical_energy=70, focus_mode="unknown")
            session.add(state)
            session.commit()
            session.refresh(state)

        original_state = {
            "mental_energy": state.mental_energy,
            "physical_energy": state.physical_energy,
            "focus_mode": state.focus_mode,
            "state_version": state.state_version,
            "recent_context": state.recent_context,
            "updated_at": state.updated_at,
            "source_last_event_id": state.source_last_event_id,
            "source_last_event_at": state.source_last_event_at,
        }

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
            session.execute(delete(StateHistory).where(StateHistory.event_id == event_id))
            session.execute(delete(EventLog).where(EventLog.event_id == event_id))
            restored_state = session.get(UserState, settings.default_user_id)
            restored_state.mental_energy = original_state["mental_energy"]
            restored_state.physical_energy = original_state["physical_energy"]
            restored_state.focus_mode = original_state["focus_mode"]
            restored_state.state_version = original_state["state_version"]
            restored_state.recent_context = original_state["recent_context"]
            restored_state.updated_at = original_state["updated_at"]
            restored_state.source_last_event_id = original_state["source_last_event_id"]
            restored_state.source_last_event_at = original_state["source_last_event_at"]
            session.add(restored_state)
            session.commit()
