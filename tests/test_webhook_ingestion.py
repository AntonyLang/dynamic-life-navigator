from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.event_log import EventLog
from app.services import event_ingestion

def test_webhook_ingest_uses_payload_occurred_at(monkeypatch, cleanup_db_artifacts, user_state_guard):
    client = TestClient(app)
    payload = {
        "id": f"webhook-{uuid4()}",
        "type": "activity",
        "occurred_at": "2026-03-13T09:15:00+08:00",
    }

    monkeypatch.setattr(event_ingestion, "claim_webhook_idempotency", lambda *args, **kwargs: True)

    response = client.post("/api/v1/webhooks/strava", json=payload)
    assert response.status_code == 200
    event_id = UUID(response.json()["event_id"])

    with SessionLocal() as session:
        try:
            event = session.get(EventLog, event_id)
            assert event is not None
            assert event.occurred_at == datetime.fromisoformat("2026-03-13T09:15:00+08:00")
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_webhook_ingest_parses_unix_millisecond_timestamp(monkeypatch, cleanup_db_artifacts, user_state_guard):
    client = TestClient(app)
    payload = {
        "id": f"webhook-{uuid4()}",
        "type": "activity",
        "timestamp": 1_741_829_200_000,
    }

    monkeypatch.setattr(event_ingestion, "claim_webhook_idempotency", lambda *args, **kwargs: True)

    response = client.post("/api/v1/webhooks/strava", json=payload)
    assert response.status_code == 200
    event_id = UUID(response.json()["event_id"])

    with SessionLocal() as session:
        try:
            event = session.get(EventLog, event_id)
            assert event is not None
            assert event.occurred_at == datetime.fromtimestamp(1_741_829_200, tz=timezone.utc)
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_webhook_ingest_falls_back_to_now_when_payload_has_no_time(monkeypatch, cleanup_db_artifacts, user_state_guard):
    client = TestClient(app)
    payload = {
        "id": f"webhook-{uuid4()}",
        "type": "activity",
    }

    monkeypatch.setattr(event_ingestion, "claim_webhook_idempotency", lambda *args, **kwargs: True)
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    response = client.post("/api/v1/webhooks/strava", json=payload)
    after = datetime.now(timezone.utc) + timedelta(seconds=1)

    assert response.status_code == 200
    event_id = UUID(response.json()["event_id"])

    with SessionLocal() as session:
        try:
            event = session.get(EventLog, event_id)
            assert event is not None
            assert before <= event.occurred_at <= after
        finally:
            cleanup_db_artifacts.event_ids(event_id)


def test_webhook_ingest_redis_duplicate_returns_existing_event(monkeypatch, cleanup_db_artifacts, user_state_guard):
    client = TestClient(app)
    external_id = f"webhook-{uuid4()}"
    payload = {
        "id": external_id,
        "type": "activity",
        "occurred_at": "2026-03-13T09:15:00+08:00",
    }
    claims = iter([True, False])

    monkeypatch.setattr(event_ingestion, "claim_webhook_idempotency", lambda *args, **kwargs: next(claims))

    first = client.post("/api/v1/webhooks/strava", json=payload)
    second = client.post("/api/v1/webhooks/strava", json=payload)

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == first.json()["event_id"]

    with SessionLocal() as session:
        try:
            rows = session.scalars(select(EventLog).where(EventLog.external_event_id == external_id)).all()
            assert len(rows) == 1
        finally:
            cleanup_db_artifacts.external_events(external_id, source="strava")


def test_webhook_ingest_degrades_to_db_only_when_redis_unavailable(monkeypatch, cleanup_db_artifacts, user_state_guard):
    client = TestClient(app)
    payload = {
        "id": f"webhook-{uuid4()}",
        "type": "activity",
    }

    monkeypatch.setattr(
        "app.core.idempotency._get_redis_client",
        lambda: (_ for _ in ()).throw(RedisConnectionError("redis unavailable")),
    )

    response = client.post("/api/v1/webhooks/strava", json=payload)
    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    event_id = UUID(response.json()["event_id"])

    with SessionLocal() as session:
        try:
            assert session.get(EventLog, event_id) is not None
        finally:
            cleanup_db_artifacts.event_ids(event_id)
