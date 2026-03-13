from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.action_node import ActionNode
from app.models.event_log import EventLog
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.recommendation_record import RecommendationRecord
from app.models.state_history import StateHistory
from app.models.user_state import UserState
from app.services.event_processing import apply_state_patch_from_event, parse_event_log

settings = get_settings()


def test_ingest_parse_state_and_recommendation_flow():
    client = TestClient(app)
    client_message_id = f"e2e-{uuid4()}"
    node_id = uuid4()
    recommendation_id = None
    event_id = None

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
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="project",
                status="active",
                title="Take a small recovery walk",
                priority_score=70,
                dynamic_urgency_score=20,
                mental_energy_required=10,
                physical_energy_required=10,
                confidence_level="medium",
            )
        )
        session.commit()

        try:
            ingest_response = client.post(
                "/api/v1/events/ingest",
                json={
                    "channel": "desktop_plugin",
                    "message_type": "text",
                    "text": "I am drained after debugging all afternoon.",
                    "client_message_id": client_message_id,
                    "occurred_at": "2026-03-13T09:00:00+08:00",
                },
            )
            assert ingest_response.status_code == 200
            event_id = UUID(ingest_response.json()["event_id"])

            parse_event_log(session, event_id)
            snapshot = apply_state_patch_from_event(session, event_id)
            assert snapshot.focus_mode == "tired"

            recommendation_response = client.get("/api/v1/recommendations/next?limit=1")
            assert recommendation_response.status_code == 200
            body = recommendation_response.json()
            recommendation_id = UUID(body["recommendation_id"])

            assert body["empty_state"] is False
            assert body["items"][0]["title"] == "Take a small recovery walk"

            refreshed_state = session.get(UserState, settings.default_user_id)
            assert refreshed_state is not None
            assert refreshed_state.source_last_event_id == event_id
            assert refreshed_state.state_version == original_state["state_version"] + 1
        finally:
            if recommendation_id is not None:
                session.execute(
                    delete(RecommendationFeedback).where(
                        RecommendationFeedback.recommendation_id == recommendation_id
                    )
                )
                session.execute(
                    delete(RecommendationRecord).where(
                        RecommendationRecord.recommendation_id == recommendation_id
                    )
                )
            if event_id is not None:
                session.execute(delete(StateHistory).where(StateHistory.event_id == event_id))
                session.execute(delete(EventLog).where(EventLog.event_id == event_id))
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
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
