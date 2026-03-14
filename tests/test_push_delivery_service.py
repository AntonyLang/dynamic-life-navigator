from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.push_delivery_attempt import PushDeliveryAttempt
from app.models.recommendation_record import RecommendationRecord
from app.services.push_delivery_service import build_push_webhook_payload, deliver_push_recommendation

settings = get_settings()


def _create_generated_push_record() -> str:
    recommendation_id = str(uuid4())
    with SessionLocal() as session:
        session.add(
            RecommendationRecord(
                recommendation_id=recommendation_id,
                user_id=settings.default_user_id,
                mode="push",
                trigger_type="state_change",
                trigger_event_id=None,
                candidate_node_ids=[],
                selected_node_ids=[],
                ranking_snapshot={"top_score": {"score": 180}},
                rendered_content={
                    "items": [
                        {
                            "node_id": str(uuid4()),
                            "title": "Take a short recovery walk",
                            "message": "A short walk can reset your focus.",
                            "reason_tags": ["state_match", "fresh_context"],
                        }
                    ]
                },
                delivery_status="generated",
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    return recommendation_id


def test_build_push_webhook_payload_uses_stable_shape(cleanup_db_artifacts):
    recommendation_id = _create_generated_push_record()

    with SessionLocal() as session:
        try:
            recommendation = session.get(RecommendationRecord, recommendation_id)
            assert recommendation is not None

            payload = build_push_webhook_payload(recommendation)

            assert payload["recommendation_id"] == recommendation_id
            assert payload["user_id"] == settings.default_user_id
            assert payload["mode"] == "push"
            assert payload["trigger_type"] == "state_change"
            assert payload["items"][0]["title"] == "Take a short recovery walk"
            assert payload["ranking_snapshot"] == {"top_score": {"score": 180}}
            assert payload["rendered_content"]["items"][0]["reason_tags"] == ["state_match", "fresh_context"]
        finally:
            cleanup_db_artifacts.recommendation_ids(recommendation_id)


def test_deliver_push_recommendation_sends_webhook_and_marks_sent(monkeypatch, cleanup_db_artifacts):
    recommendation_id = _create_generated_push_record()
    captured: dict[str, object] = {}

    class DummyResponse:
        status_code = 202
        text = '{"accepted": true}'

        def json(self):
            return {"accepted": True}

    class DummyClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, *, headers: dict[str, str], content: bytes):
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return DummyResponse()

    monkeypatch.setenv("PUSH_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("PUSH_WEBHOOK_URL", "https://example.test/push")
    monkeypatch.setenv("PUSH_WEBHOOK_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("PUSH_DELIVERY_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.push_delivery_service.httpx.Client", DummyClient)

    with SessionLocal() as session:
        try:
            result = deliver_push_recommendation(session, recommendation_id)

            assert result["status"] == "sent"
            assert result["attempt_count"] == 1
            assert captured["url"] == "https://example.test/push"
            assert captured["trust_env"] is False
            assert captured["timeout"] == 7.0
            assert captured["headers"]["Content-Type"] == "application/json; charset=utf-8"
            assert captured["headers"]["X-Recommendation-Id"] == recommendation_id
            assert captured["content"]

            recommendation = session.get(RecommendationRecord, recommendation_id)
            assert recommendation is not None
            assert recommendation.delivery_status == "sent"

            attempts = session.scalars(
                select(PushDeliveryAttempt).where(PushDeliveryAttempt.recommendation_id == recommendation_id)
            ).all()
            assert len(attempts) == 1
            assert attempts[0].delivery_status == "sent"
            assert attempts[0].response_status_code == 202
            assert attempts[0].response_payload == {"accepted": True}
        finally:
            cleanup_db_artifacts.recommendation_ids(recommendation_id)
            get_settings.cache_clear()


def test_deliver_push_recommendation_skips_when_webhook_url_missing(monkeypatch, cleanup_db_artifacts):
    recommendation_id = _create_generated_push_record()

    monkeypatch.setenv("PUSH_DELIVERY_ENABLED", "true")
    monkeypatch.delenv("PUSH_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()

    with SessionLocal() as session:
        try:
            result = deliver_push_recommendation(session, recommendation_id)

            assert result["status"] == "skipped"
            assert result["reason"] == "missing_webhook_url"

            recommendation = session.get(RecommendationRecord, recommendation_id)
            assert recommendation is not None
            assert recommendation.delivery_status == "skipped"

            attempts = session.scalars(
                select(PushDeliveryAttempt).where(PushDeliveryAttempt.recommendation_id == recommendation_id)
            ).all()
            assert len(attempts) == 1
            assert attempts[0].delivery_status == "skipped"
            assert attempts[0].error_code == "missing_webhook_url"
        finally:
            cleanup_db_artifacts.recommendation_ids(recommendation_id)
            get_settings.cache_clear()


def test_deliver_push_recommendation_retries_and_marks_failed(monkeypatch, cleanup_db_artifacts):
    recommendation_id = _create_generated_push_record()
    sleep_calls: list[int] = []

    class DummyClient:
        def __init__(self, *, timeout: float, trust_env: bool) -> None:
            self.timeout = timeout
            self.trust_env = trust_env

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url: str, *, headers: dict[str, str], content: bytes):
            raise RuntimeError("unexpected")

    class FailingTransportClient(DummyClient):
        def post(self, url: str, *, headers: dict[str, str], content: bytes):
            from app.services.push_delivery_service import httpx

            raise httpx.ConnectError("connection failed")

    monkeypatch.setenv("PUSH_DELIVERY_ENABLED", "true")
    monkeypatch.setenv("PUSH_WEBHOOK_URL", "https://example.test/push")
    monkeypatch.setenv("PUSH_DELIVERY_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.push_delivery_service.httpx.Client", FailingTransportClient)

    with SessionLocal() as session:
        try:
            result = deliver_push_recommendation(session, recommendation_id, sleep_fn=lambda seconds: sleep_calls.append(seconds))

            assert result["status"] == "failed"
            assert result["attempt_count"] == 3
            assert result["reason"] == "ConnectError"
            assert sleep_calls == [1, 2]

            recommendation = session.get(RecommendationRecord, recommendation_id)
            assert recommendation is not None
            assert recommendation.delivery_status == "failed"

            attempts = session.scalars(
                select(PushDeliveryAttempt)
                .where(PushDeliveryAttempt.recommendation_id == recommendation_id)
                .order_by(PushDeliveryAttempt.attempt_number.asc())
            ).all()
            assert len(attempts) == 3
            assert [attempt.delivery_status for attempt in attempts] == ["failed", "failed", "failed"]
            assert attempts[-1].error_code == "ConnectError"
        finally:
            cleanup_db_artifacts.recommendation_ids(recommendation_id)
            get_settings.cache_clear()
