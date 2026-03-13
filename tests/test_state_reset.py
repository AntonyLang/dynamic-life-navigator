from __future__ import annotations

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.services.state_service import reset_state

settings = get_settings()


def test_reset_state_uses_cas_and_writes_history():
    reason = f"manual-reset-{settings.default_user_id}"

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

        try:
            snapshot = reset_state(session, 75, 80, reason)
            refreshed = session.get(UserState, settings.default_user_id)
            history = session.scalar(
                select(StateHistory)
                .where(StateHistory.user_id == settings.default_user_id, StateHistory.change_reason == reason)
                .order_by(StateHistory.created_at.desc())
                .limit(1)
            )

            assert snapshot.mental_energy == 75
            assert snapshot.physical_energy == 80
            assert refreshed is not None
            assert refreshed.state_version == original_state["state_version"] + 1
            assert history is not None
            assert history.before_state["mental_energy"] == original_state["mental_energy"]
            assert history.after_state["mental_energy"] == 75
        finally:
            session.execute(delete(StateHistory).where(StateHistory.change_reason == reason))
            restored = session.get(UserState, settings.default_user_id)
            restored.mental_energy = original_state["mental_energy"]
            restored.physical_energy = original_state["physical_energy"]
            restored.focus_mode = original_state["focus_mode"]
            restored.state_version = original_state["state_version"]
            restored.recent_context = original_state["recent_context"]
            restored.updated_at = original_state["updated_at"]
            restored.source_last_event_id = original_state["source_last_event_id"]
            restored.source_last_event_at = original_state["source_last_event_at"]
            session.add(restored)
            session.commit()


def test_reset_state_retries_on_compare_and_swap_conflict(monkeypatch):
    reason = f"manual-reset-cas-{settings.default_user_id}"

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
            snapshot = reset_state(session, 65, 68, reason, max_retries=3)
            refreshed = session.get(UserState, settings.default_user_id)

            assert call_count["updates"] >= 2
            assert snapshot.mental_energy == 65
            assert refreshed is not None
            assert refreshed.state_version == original_state["state_version"] + 1
        finally:
            session.execute(delete(StateHistory).where(StateHistory.change_reason == reason))
            restored = session.get(UserState, settings.default_user_id)
            restored.mental_energy = original_state["mental_energy"]
            restored.physical_energy = original_state["physical_energy"]
            restored.focus_mode = original_state["focus_mode"]
            restored.state_version = original_state["state_version"]
            restored.recent_context = original_state["recent_context"]
            restored.updated_at = original_state["updated_at"]
            restored.source_last_event_id = original_state["source_last_event_id"]
            restored.source_last_event_at = original_state["source_last_event_at"]
            session.add(restored)
            session.commit()
