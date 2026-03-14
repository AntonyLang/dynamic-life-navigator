from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.action_node import ActionNode
from app.models.event_log import EventLog
from app.models.node_annotation import NodeAnnotation
from app.models.recommendation_record import RecommendationRecord
from app.models.user_state import UserState
from app.services.push_service import evaluate_push_opportunities
from app.workers import local_pipeline
from app.workers import tasks_push_delivery
from app.workers import tasks_push_eval
from app.workers import tasks_state

settings = get_settings()


def test_push_evaluation_generates_record_for_strong_candidate(user_state_guard):
    node_id = uuid4()
    trigger_event_id = uuid4()

    with SessionLocal() as session:
        session.execute(
            delete(NodeAnnotation).where(
                NodeAnnotation.source == "test",
                NodeAnnotation.annotation_type == "context",
            )
        )
        session.execute(
            delete(ActionNode).where(ActionNode.title == "High-signal push candidate")
        )
        session.execute(
            delete(RecommendationRecord).where(
                RecommendationRecord.mode == "push",
                RecommendationRecord.trigger_type == "state_change",
            )
        )
        session.commit()

        state = session.get(UserState, settings.default_user_id)

        state.mental_energy = 85
        state.physical_energy = 85
        state.do_not_disturb_until = None
        session.add(state)
        session.add(
            EventLog(
                event_id=trigger_event_id,
                user_id=settings.default_user_id,
                source="desktop_plugin",
                source_event_type="text",
                external_event_id=str(trigger_event_id),
                payload_hash=str(trigger_event_id),
                raw_text="push trigger",
                raw_payload={"text": "push trigger"},
                occurred_at=datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            ActionNode(
                node_id=node_id,
                user_id=settings.default_user_id,
                drive_type="project",
                status="active",
                title="High-signal push candidate",
                priority_score=95,
                dynamic_urgency_score=85,
                mental_energy_required=20,
                physical_energy_required=10,
                confidence_level="high",
            )
        )
        session.add(
            NodeAnnotation(
                node_id=node_id,
                annotation_type="context",
                content={"note": "fresh push context"},
                source="test",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
            )
        )
        session.commit()

        try:
            result = evaluate_push_opportunities(session, trigger_event_id)
            assert result["status"] == "generated"

            record = session.scalar(
                select(RecommendationRecord).where(
                    RecommendationRecord.recommendation_id == result["recommendation_id"]
                )
            )
            assert record is not None
            assert record.mode == "push"
            assert record.delivery_status == "generated"
            assert node_id in record.selected_node_ids
        finally:
            session.execute(
                delete(RecommendationRecord).where(
                    RecommendationRecord.trigger_event_id == trigger_event_id
                )
            )
            session.execute(delete(NodeAnnotation).where(NodeAnnotation.node_id == node_id))
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.execute(delete(EventLog).where(EventLog.event_id == trigger_event_id))
            session.commit()


def test_push_evaluation_skips_when_do_not_disturb_active(user_state_guard):
    trigger_event_id = uuid4()

    with SessionLocal() as session:
        session.execute(
            delete(RecommendationRecord).where(
                RecommendationRecord.mode == "push",
                RecommendationRecord.trigger_type == "state_change",
            )
        )
        session.commit()

        state = session.get(UserState, settings.default_user_id)

        state.do_not_disturb_until = datetime.now(timezone.utc) + timedelta(hours=1)
        session.add(state)
        session.add(
            EventLog(
                event_id=trigger_event_id,
                user_id=settings.default_user_id,
                source="desktop_plugin",
                source_event_type="text",
                external_event_id=str(trigger_event_id),
                payload_hash=str(trigger_event_id),
                raw_text="push trigger",
                raw_payload={"text": "push trigger"},
                occurred_at=datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        try:
            result = evaluate_push_opportunities(session, trigger_event_id)
            assert result["status"] == "skipped"
            assert result["reason"] == "do_not_disturb"

            record = session.scalar(
                select(RecommendationRecord).where(
                    RecommendationRecord.recommendation_id == result["recommendation_id"]
                )
            )
            assert record is not None
            assert record.mode == "push"
            assert record.delivery_status == "skipped"
            assert record.rendered_content["skip_reason"] == "do_not_disturb"
        finally:
            session.execute(
                delete(RecommendationRecord).where(
                    RecommendationRecord.trigger_event_id == trigger_event_id
                )
            )
            session.execute(delete(EventLog).where(EventLog.event_id == trigger_event_id))
            session.commit()


def test_apply_state_patch_task_enqueues_push_evaluation(monkeypatch):
    captured: dict[str, str | None] = {"push_event_id": None, "compare_event_id": None}

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummySnapshot:
        focus_mode = "focused"
        mental_energy = 55
        physical_energy = 65

    monkeypatch.setattr(tasks_state, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(tasks_state, "apply_state_patch_from_event", lambda session, event_id: DummySnapshot())
    monkeypatch.setattr(tasks_state.celery_app.conf, "task_always_eager", False, raising=False)

    def fake_delay(event_id: str) -> None:
        captured["push_event_id"] = event_id

    monkeypatch.setattr(tasks_push_eval.evaluate_push_opportunities, "delay", fake_delay)
    monkeypatch.setattr("app.workers.tasks_compare.compare_parser_decision.delay", lambda event_id: captured.__setitem__("compare_event_id", event_id))

    result = tasks_state.apply_state_patch("evt-worker-1")

    assert result["status"] == "applied"
    assert captured["push_event_id"] == "evt-worker-1"
    assert captured["compare_event_id"] == "evt-worker-1"


def test_push_evaluation_task_enqueues_delivery_for_generated_push(monkeypatch):
    captured: dict[str, str | None] = {"recommendation_id": None}

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(tasks_push_eval, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(
        tasks_push_eval,
        "evaluate_push_opportunities_service",
        lambda session, trigger_event_id: {
            "status": "generated",
            "recommendation_id": "rec-push-1",
            "trigger_event_id": trigger_event_id,
            "reason": None,
        },
    )
    monkeypatch.setattr(tasks_push_eval.celery_app.conf, "task_always_eager", False, raising=False)
    monkeypatch.setattr(
        tasks_push_delivery.deliver_push_recommendation,
        "delay",
        lambda recommendation_id: captured.__setitem__("recommendation_id", recommendation_id),
    )

    result = tasks_push_eval.evaluate_push_opportunities("evt-push-1")

    assert result["status"] == "generated"
    assert result["delivery_status"] == "queued"
    assert captured["recommendation_id"] == "rec-push-1"


def test_local_pipeline_runs_push_delivery_after_generated_result(monkeypatch):
    captured: dict[str, object] = {"recommendation_id": None, "delivery_status": None}

    class DummySession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummySnapshot:
        focus_mode = "tired"
        mental_energy = 65
        physical_energy = 80

    monkeypatch.setattr(local_pipeline, "SessionLocal", lambda: DummySession())
    monkeypatch.setattr(local_pipeline, "parse_event_log", lambda session, event_id: {"event_type": "chat_update"})
    monkeypatch.setattr(local_pipeline, "apply_state_patch_from_event", lambda session, event_id: DummySnapshot())
    monkeypatch.setattr(
        local_pipeline,
        "evaluate_push_opportunities",
        lambda session, event_id: {
            "status": "generated",
            "recommendation_id": "rec-local-1",
            "trigger_event_id": event_id,
            "reason": None,
        },
    )
    monkeypatch.setattr(
        local_pipeline,
        "deliver_push_recommendation",
        lambda session, recommendation_id: (
            captured.__setitem__("recommendation_id", recommendation_id)
            or {"status": "sent", "recommendation_id": recommendation_id}
        ),
    )
    monkeypatch.setattr(local_pipeline, "compare_shadow_parser_decision", lambda session, event_id: {"status": "skipped"})
    monkeypatch.setattr(local_pipeline, "get_settings", lambda: SimpleNamespace(parser_shadow_enabled=False))

    local_pipeline.run_local_event_pipeline("evt-local-1")

    assert captured["recommendation_id"] == "rec-local-1"
