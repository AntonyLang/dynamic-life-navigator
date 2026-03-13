"""State service implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
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


def reset_state(
    db: Session,
    mental_energy: int,
    physical_energy: int,
    reason: str,
    *,
    max_retries: int = 3,
) -> UserStateSnapshot:
    """Reset the persisted user state and write a history row."""

    state = _ensure_user_state(db)

    for _ in range(max_retries):
        state = db.get(UserState, state.user_id)
        expected_version = state.state_version
        before_snapshot = _snapshot_from_model(state).model_dump(mode="json")
        now = datetime.now(timezone.utc)

        result = db.execute(
            update(UserState)
            .where(
                UserState.user_id == state.user_id,
                UserState.state_version == expected_version,
            )
            .values(
                state_version=expected_version + 1,
                mental_energy=mental_energy,
                physical_energy=physical_energy,
                focus_mode="recovered",
                recent_context="manual reset",
                updated_at=now,
            )
        )
        if result.rowcount == 1:
            updated_state = db.scalar(select(UserState).where(UserState.user_id == state.user_id))
            db.add(
                StateHistory(
                    user_id=updated_state.user_id,
                    event_id=None,
                    before_state=before_snapshot,
                    after_state=_snapshot_from_model(updated_state).model_dump(mode="json"),
                    change_reason=reason,
                )
            )
            db.commit()
            return _snapshot_from_model(updated_state)

        db.rollback()

    raise RuntimeError(f"failed to reset state for user {state.user_id} after {max_retries} retries")
