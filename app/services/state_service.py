"""State service implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.common import UserStateSnapshot

settings = get_settings()


def _snapshot_from_model(state: UserState) -> UserStateSnapshot:
    """Map a persisted user state row into the API snapshot schema."""

    return UserStateSnapshot(
        mental_energy=state.mental_energy,
        physical_energy=state.physical_energy,
        focus_mode=state.focus_mode,
        do_not_disturb_until=state.do_not_disturb_until,
        recent_context=state.recent_context,
        last_updated_at=state.updated_at,
    )


def _ensure_user_state(db: Session) -> UserState:
    """Ensure the default MVP user has a snapshot row."""

    state = db.get(UserState, settings.default_user_id)
    if state is None:
        state = UserState(user_id=settings.default_user_id)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def get_current_state(db: Session) -> UserStateSnapshot:
    """Return the current persisted user state snapshot."""

    state = _ensure_user_state(db)
    return _snapshot_from_model(state)


def reset_state(db: Session, mental_energy: int, physical_energy: int, reason: str) -> UserStateSnapshot:
    """Reset the persisted user state and write a history row."""

    state = _ensure_user_state(db)
    before_snapshot = _snapshot_from_model(state).model_dump(mode="json")

    state.mental_energy = mental_energy
    state.physical_energy = physical_energy
    state.focus_mode = "recovered"
    state.recent_context = "manual reset"
    state.updated_at = datetime.now(timezone.utc)
    state.state_version += 1

    db.add(
        StateHistory(
            user_id=state.user_id,
            event_id=None,
            before_state=before_snapshot,
            after_state=_snapshot_from_model(state).model_dump(mode="json"),
            change_reason=reason,
        )
    )
    db.add(state)
    db.commit()
    db.refresh(state)

    return _snapshot_from_model(state)
