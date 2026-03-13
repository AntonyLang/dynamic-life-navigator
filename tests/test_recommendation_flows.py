from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.action_node import ActionNode
from app.models.node_annotation import NodeAnnotation
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.recommendation_record import RecommendationRecord
from app.models.user_state import UserState

settings = get_settings()


def test_brief_route_returns_persisted_summary():
    client = TestClient(app)
    node_ids: list = []

    with SessionLocal() as session:
        project_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="Finish state reducer",
            dynamic_urgency_score=90,
            ddl_timestamp=datetime.now(timezone.utc) + timedelta(hours=12),
        )
        value_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="value",
            status="active",
            title="Evening recovery walk",
            dynamic_urgency_score=10,
        )
        node_ids = [project_node.node_id, value_node.node_id]

        session.add_all([project_node, value_node])
        session.add(
            NodeAnnotation(
                node_id=project_node.node_id,
                annotation_type="context",
                content={"note": "Fresh note"},
                source="test",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.commit()

        try:
            response = client.get("/api/v1/recommendations/brief")
            assert response.status_code == 200

            body = response.json()
            assert body["summary"]["active_projects"] >= 1
            assert body["summary"]["active_values"] >= 1
            assert body["summary"]["urgent_nodes"] >= 1
            assert body["summary"]["stale_nodes"] >= 1
            assert any(item["title"] == "Finish state reducer" for item in body["items"])
            assert any(item["health"] in {"urgent", "stale", "stable", "cooldown"} for item in body["items"])
        finally:
            session.execute(delete(NodeAnnotation).where(NodeAnnotation.node_id.in_(node_ids)))
            session.execute(delete(ActionNode).where(ActionNode.node_id.in_(node_ids)))
            session.commit()


def test_pull_feedback_flow_persists_records():
    client = TestClient(app)
    node_ids: list = []

    with SessionLocal() as session:
        recommendation_id = None
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

        state.mental_energy = 45
        state.physical_energy = 70
        session.add(state)

        best_fit_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="Draft the next API step",
            priority_score=75,
            dynamic_urgency_score=60,
            mental_energy_required=35,
            physical_energy_required=10,
            confidence_level="high",
        )
        rejected_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="Return to the rejected refactor",
            priority_score=90,
            dynamic_urgency_score=70,
            mental_energy_required=30,
            physical_energy_required=10,
            last_rejected_at=datetime.now(timezone.utc) - timedelta(hours=4),
        )
        filtered_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="Deep architecture rewrite",
            priority_score=95,
            dynamic_urgency_score=80,
            mental_energy_required=95,
            physical_energy_required=15,
        )
        node_ids = [best_fit_node.node_id, rejected_node.node_id, filtered_node.node_id]

        session.add_all([best_fit_node, rejected_node, filtered_node])
        session.add(
            NodeAnnotation(
                node_id=best_fit_node.node_id,
                annotation_type="context",
                content={"note": "Fresh context"},
                source="test",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.commit()

        try:
            response = client.get("/api/v1/recommendations/pull?limit=2")
            assert response.status_code == 200

            body = response.json()
            recommendation_id = UUID(body["recommendation_id"])
            assert body["empty_state"] is False
            assert len(body["items"]) >= 1
            assert body["items"][0]["title"] == "Draft the next API step"
            assert "state_match" in body["items"][0]["reason_tags"]

            feedback_response = client.post(
                f"/api/v1/recommendations/{recommendation_id}/feedback",
                json={"feedback": "accepted", "node_id": str(best_fit_node.node_id), "channel": "desktop"},
            )
            assert feedback_response.status_code == 200

            persisted_record = session.scalar(
                select(RecommendationRecord).where(RecommendationRecord.recommendation_id == recommendation_id)
            )
            persisted_feedback = session.scalar(
                select(RecommendationFeedback).where(
                    RecommendationFeedback.recommendation_id == recommendation_id,
                    RecommendationFeedback.feedback == "accepted",
                )
            )

            assert persisted_record is not None
            assert persisted_record.mode == "pull"
            assert best_fit_node.node_id in persisted_record.selected_node_ids
            assert filtered_node.node_id not in persisted_record.candidate_node_ids
            assert persisted_feedback is not None
            assert persisted_feedback.channel == "desktop"
            session.refresh(best_fit_node)
            assert best_fit_node.last_completed_at is not None
            assert best_fit_node.last_rejected_at is None
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
            session.execute(delete(NodeAnnotation).where(NodeAnnotation.node_id.in_(node_ids)))
            session.execute(delete(ActionNode).where(ActionNode.node_id.in_(node_ids)))
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


def test_rejected_feedback_updates_node_penalty_signal():
    client = TestClient(app)
    node_id = uuid4()

    with SessionLocal() as session:
        recommendation_id = None
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

        state.mental_energy = 60
        state.physical_energy = 60
        session.add(state)
        node = ActionNode(
            node_id=node_id,
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="A rejectable candidate",
            priority_score=80,
            dynamic_urgency_score=50,
            mental_energy_required=20,
            physical_energy_required=10,
        )
        session.add(node)
        session.commit()

        try:
            response = client.get("/api/v1/recommendations/pull?limit=1")
            assert response.status_code == 200
            recommendation_id = UUID(response.json()["recommendation_id"])

            feedback_response = client.post(
                f"/api/v1/recommendations/{recommendation_id}/feedback",
                json={"feedback": "rejected", "node_id": str(node_id), "channel": "desktop"},
            )
            assert feedback_response.status_code == 200

            session.refresh(node)
            assert node.last_rejected_at is not None
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
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
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


def test_feedback_rejects_node_outside_recommendation():
    client = TestClient(app)
    node_ids: list = []

    with SessionLocal() as session:
        recommendation_id = None
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

        state.mental_energy = 70
        state.physical_energy = 70
        session.add(state)

        recommended_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="Included candidate",
            priority_score=85,
            dynamic_urgency_score=55,
            mental_energy_required=15,
            physical_energy_required=10,
        )
        unrelated_node = ActionNode(
            node_id=uuid4(),
            user_id=settings.default_user_id,
            drive_type="project",
            status="active",
            title="Unrelated candidate",
            priority_score=10,
            dynamic_urgency_score=0,
            mental_energy_required=95,
            physical_energy_required=95,
        )
        node_ids = [recommended_node.node_id, unrelated_node.node_id]
        session.add_all([recommended_node, unrelated_node])
        session.commit()

        try:
            response = client.get("/api/v1/recommendations/pull?limit=1")
            assert response.status_code == 200
            recommendation_id = UUID(response.json()["recommendation_id"])

            feedback_response = client.post(
                f"/api/v1/recommendations/{recommendation_id}/feedback",
                json={"feedback": "rejected", "node_id": str(unrelated_node.node_id), "channel": "desktop"},
            )
            assert feedback_response.status_code == 400
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
            session.execute(delete(ActionNode).where(ActionNode.node_id.in_(node_ids)))
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


def test_pull_returns_fallback_when_no_candidate_matches_energy():
    client = TestClient(app)
    node_id = uuid4()

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

        state.mental_energy = 5
        state.physical_energy = 5
        session.add(state)
        session.add(
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="project",
                status="active",
                title="Impossible high-energy task",
                mental_energy_required=90,
                physical_energy_required=90,
                priority_score=99,
                dynamic_urgency_score=99,
            )
        )
        session.commit()

        recommendation_id = None
        try:
            response = client.get("/api/v1/recommendations/pull?limit=1")
            assert response.status_code == 200
            body = response.json()
            recommendation_id = UUID(body["recommendation_id"])

            assert body["empty_state"] is True
            assert not body["items"]
            assert "low-effort" in body["fallback_message"]
        finally:
            if recommendation_id is not None:
                session.execute(
                    delete(RecommendationRecord).where(
                        RecommendationRecord.recommendation_id == recommendation_id
                    )
                )
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
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
