"""Deterministic event parsing and state patch application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models.event_log import EventLog
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.schemas.common import UserStateSnapshot
from app.services.state_service import _ensure_user_state, _snapshot_from_model

logger = logging.getLogger(__name__)


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


@dataclass(slots=True)
class ParseResult:
    """Structured parse result with explicit status."""

    impact: ParsedImpact | None
    status: str


def _clamp_energy(value: int) -> int:
    return max(0, min(100, value))


def _parse_from_event(event: EventLog) -> ParseResult:
    """Build a conservative deterministic impact from an event log."""

    text = (event.raw_text or "").strip()
    lowered = text.lower()

    if not text and not event.raw_payload:
        return ParseResult(impact=None, status="failed")

    summary = text[:300] if text else f"{event.source} event received"
    should_offer_pull_hint = False

    if any(token in lowered for token in ("debug", "experiment", "study", "coding", "burned", "drained", "tired")):
        return ParseResult(
            impact=ParsedImpact(
                event_summary=summary,
                event_type="chat_update",
                mental_delta=-20,
                physical_delta=0,
                focus_mode="tired",
                tags=["mental_load"],
                should_offer_pull_hint=True,
                confidence=0.7,
            ),
            status="success",
        )

    if any(token in lowered for token in ("sleep", "nap", "rest", "recovered", "break")):
        return ParseResult(
            impact=ParsedImpact(
                event_summary=summary,
                event_type="rest",
                mental_delta=15,
                physical_delta=10,
                focus_mode="recovered",
                tags=["recovery"],
                should_offer_pull_hint=False,
                confidence=0.7,
            ),
            status="success",
        )

    if any(token in lowered for token in ("walk", "ride", "run", "exercise", "workout")):
        return ParseResult(
            impact=ParsedImpact(
                event_summary=summary,
                event_type="exercise",
                mental_delta=10,
                physical_delta=-15,
                focus_mode="recovered",
                tags=["movement", "recovery"],
                should_offer_pull_hint=True,
                confidence=0.7,
            ),
            status="success",
        )

    if event.source in {"github", "calendar", "strava"}:
        return ParseResult(
            impact=ParsedImpact(
                event_summary=summary,
                event_type=event.source,
                mental_delta=0,
                physical_delta=0,
                focus_mode="unknown",
                tags=[event.source],
                should_offer_pull_hint=False,
                confidence=0.45,
            ),
            status="fallback",
        )

    if text:
        return ParseResult(
            impact=ParsedImpact(
                event_summary=summary,
                event_type="other",
                mental_delta=0,
                physical_delta=0,
                focus_mode="unknown",
                tags=[],
                should_offer_pull_hint=False,
                confidence=0.3,
            ),
            status="fallback",
        )

    return ParseResult(impact=None, status="failed")


def parse_event_log(db: Session, event_id: UUID | str) -> dict[str, Any]:
    """Parse a persisted event into a minimal structured impact."""

    event = db.get(EventLog, event_id)
    if event is None:
        raise ValueError(f"event {event_id} not found")

    result = _parse_from_event(event)
    event.parsed_impact = result.impact.as_dict() if result.impact is not None else {}
    event.parse_status = result.status
    db.add(event)
    db.commit()
    db.refresh(event)
    log_event(
        logger,
        logging.INFO,
        "event parsed",
        event_id=event.event_id,
        user_id=event.user_id,
        parse_status=event.parse_status,
        event_type=event.parsed_impact.get("event_type") if event.parsed_impact else None,
    )
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
    if event.parse_status == "failed" or not event.parsed_impact:
        log_event(
            logger,
            logging.INFO,
            "state patch skipped after parse failure",
            event_id=event.event_id,
            user_id=state.user_id,
            parse_status=event.parse_status,
            state_version=state.state_version,
        )
        return _snapshot_from_model(state)

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
            log_event(
                logger,
                logging.INFO,
                "state patch applied",
                event_id=event.event_id,
                user_id=updated_state.user_id,
                parse_status=event.parse_status,
                state_version=updated_state.state_version,
            )
            return _snapshot_from_model(updated_state)

        db.rollback()

    raise RuntimeError(f"failed to apply state patch for event {event_id} after {max_retries} retries")
