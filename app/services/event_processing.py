"""Deterministic event parsing and state patch application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.common import UserStateSnapshot
from app.services.state_service import _ensure_user_state, _snapshot_from_model


@dataclass(slots=True)
class ParsedImpact:
    """Minimal structured impact derived from an event log."""

    event_summary: str
    event_type: str
    mental_delta: int
    physical_delta: int
    focus_mode: str
    tags: list[str]
    should_offer_pull_hint: bool
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_summary": self.event_summary,
            "event_type": self.event_type,
            "mental_delta": self.mental_delta,
            "physical_delta": self.physical_delta,
            "focus_mode": self.focus_mode,
            "tags": self.tags,
            "should_offer_pull_hint": self.should_offer_pull_hint,
            "confidence": self.confidence,
        }


def _clamp_energy(value: int) -> int:
    return max(0, min(100, value))


def _parse_from_text(text: str | None, source: str) -> ParsedImpact:
    """Build a conservative deterministic impact from raw text."""

    lowered = (text or "").lower()
    event_type = "other"
    mental_delta = 0
    physical_delta = 0
    focus_mode = "unknown"
    tags: list[str] = []
    summary = text.strip() if text else f"{source} event received"
    should_offer_pull_hint = False

    if any(token in lowered for token in ("debug", "experiment", "study", "coding", "burned", "drained", "tired")):
        event_type = "chat_update"
        mental_delta = -20
        focus_mode = "tired"
        tags.append("mental_load")
        should_offer_pull_hint = True
    elif any(token in lowered for token in ("sleep", "nap", "rest", "recovered", "break")):
        event_type = "rest"
        mental_delta = 15
        physical_delta = 10
        focus_mode = "recovered"
        tags.append("recovery")
    elif any(token in lowered for token in ("walk", "ride", "run", "exercise", "workout")):
        event_type = "exercise"
        mental_delta = 10
        physical_delta = -15
        focus_mode = "recovered"
        tags.extend(["movement", "recovery"])
        should_offer_pull_hint = True
    elif source in {"github", "calendar", "strava"}:
        event_type = source
        tags.append(source)

    return ParsedImpact(
        event_summary=summary[:300],
        event_type=event_type,
        mental_delta=mental_delta,
        physical_delta=physical_delta,
        focus_mode=focus_mode,
        tags=tags,
        should_offer_pull_hint=should_offer_pull_hint,
        confidence=0.45,
    )


def parse_event_log(db: Session, event_id: UUID | str) -> dict[str, Any]:
    """Parse a persisted event into a minimal structured impact."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    impact = _parse_from_text(event.raw_text, event.source)
    event.parsed_impact = impact.as_dict()
    event.parse_status = "fallback"
    db.add(event)
    db.commit()
    db.refresh(event)
    return event.parsed_impact


def apply_state_patch_from_event(
    db: Session,
    event_id: UUID | str,
    *,
    max_retries: int = 2,
) -> UserStateSnapshot:
    """Apply a deterministic state patch using optimistic concurrency."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    if not event.parsed_impact:
        parse_event_log(db, event_id)
        db.refresh(event)

    state = _ensure_user_state(db)

    impact = event.parsed_impact
    for _ in range(max_retries):
        state = db.get(UserState, state.user_id)
        expected_version = state.state_version
        before_snapshot = _snapshot_from_model(state).model_dump(mode="json")

        new_mental = _clamp_energy(state.mental_energy + int(impact.get("mental_delta", 0)))
        new_physical = _clamp_energy(state.physical_energy + int(impact.get("physical_delta", 0)))
        new_focus = impact.get("focus_mode") or state.focus_mode
        now = datetime.now(timezone.utc)

        result = db.execute(
            update(UserState)
            .where(
                UserState.user_id == state.user_id,
                UserState.state_version == expected_version,
            )
            .values(
                state_version=expected_version + 1,
                mental_energy=new_mental,
                physical_energy=new_physical,
                focus_mode=new_focus,
                recent_context=impact.get("event_summary"),
                source_last_event_id=event.event_id,
                source_last_event_at=event.occurred_at,
                updated_at=now,
            )
        )
        if result.rowcount == 1:
            updated_state = db.scalar(select(UserState).where(UserState.user_id == state.user_id))
            db.add(
                StateHistory(
                    user_id=updated_state.user_id,
                    event_id=event.event_id,
                    before_state=before_snapshot,
                    after_state=_snapshot_from_model(updated_state).model_dump(mode="json"),
                    change_reason="event_patch",
                )
            )
            db.commit()
            return _snapshot_from_model(updated_state)

        db.rollback()

    raise RuntimeError(f"failed to apply state patch for event {event_id} after {max_retries} retries")
