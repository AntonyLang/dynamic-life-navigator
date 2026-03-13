from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event_log import EventLog
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.recommendation_record import RecommendationRecord
from app.models.state_history import StateHistory
from app.models.user_state import UserState

settings = get_settings()


def _ensure_user_state(session) -> UserState:
    state = session.get(UserState, settings.default_user_id)
    if state is None:
        state = UserState(user_id=settings.default_user_id)
        session.add(state)
        session.commit()
        session.refresh(state)
    return state


def snapshot_user_state() -> dict[str, Any]:
    with SessionLocal() as session:
        state = _ensure_user_state(session)
        return {
            "mental_energy": state.mental_energy,
            "physical_energy": state.physical_energy,
            "focus_mode": state.focus_mode,
            "state_version": state.state_version,
            "do_not_disturb_until": state.do_not_disturb_until,
            "recent_context": state.recent_context,
            "updated_at": state.updated_at,
            "source_last_event_id": state.source_last_event_id,
            "source_last_event_at": state.source_last_event_at,
        }


def restore_user_state(snapshot: dict[str, Any]) -> None:
    with SessionLocal() as session:
        state = _ensure_user_state(session)
        state.mental_energy = snapshot["mental_energy"]
        state.physical_energy = snapshot["physical_energy"]
        state.focus_mode = snapshot["focus_mode"]
        state.state_version = snapshot["state_version"]
        state.do_not_disturb_until = snapshot["do_not_disturb_until"]
        state.recent_context = snapshot["recent_context"]
        state.updated_at = snapshot["updated_at"]
        state.source_last_event_id = snapshot["source_last_event_id"]
        state.source_last_event_at = snapshot["source_last_event_at"]
        session.add(state)
        session.commit()


class CleanupDbArtifacts:
    @staticmethod
    def recommendation_ids(*recommendation_ids: Any) -> None:
        ids = [recommendation_id for recommendation_id in recommendation_ids if recommendation_id is not None]
        if not ids:
            return

        with SessionLocal() as session:
            session.execute(delete(RecommendationFeedback).where(RecommendationFeedback.recommendation_id.in_(ids)))
            session.execute(delete(RecommendationRecord).where(RecommendationRecord.recommendation_id.in_(ids)))
            session.commit()

    @staticmethod
    def event_ids(*event_ids: Any) -> None:
        ids = [event_id for event_id in event_ids if event_id is not None]
        if not ids:
            return

        with SessionLocal() as session:
            recommendation_ids = session.scalars(
                select(RecommendationRecord.recommendation_id).where(RecommendationRecord.trigger_event_id.in_(ids))
            ).all()
            if recommendation_ids:
                session.execute(
                    delete(RecommendationFeedback).where(RecommendationFeedback.recommendation_id.in_(recommendation_ids))
                )
            session.execute(delete(RecommendationRecord).where(RecommendationRecord.trigger_event_id.in_(ids)))
            session.execute(delete(StateHistory).where(StateHistory.event_id.in_(ids)))
            session.execute(delete(EventLog).where(EventLog.event_id.in_(ids)))
            session.commit()

    @staticmethod
    def external_events(*external_event_ids: str, source: str | None = None) -> None:
        ids = [external_event_id for external_event_id in external_event_ids if external_event_id]
        if not ids:
            return

        with SessionLocal() as session:
            query = select(EventLog.event_id).where(EventLog.external_event_id.in_(ids))
            if source is not None:
                query = query.where(EventLog.source == source)
            event_ids = session.scalars(query).all()

        CleanupDbArtifacts.event_ids(*event_ids)


@pytest.fixture
def user_state_guard() -> Iterable[dict[str, Any]]:
    snapshot = snapshot_user_state()
    yield snapshot
    restore_user_state(snapshot)


@pytest.fixture
def cleanup_db_artifacts() -> CleanupDbArtifacts:
    return CleanupDbArtifacts()
