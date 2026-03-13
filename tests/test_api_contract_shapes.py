from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_state_route_returns_contract_shape():
    client = TestClient(app)

    response = client.get("/api/v1/state")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert "state" in body
    assert set(body["state"]).issuperset(
        {
            "mental_energy",
            "physical_energy",
            "focus_mode",
            "do_not_disturb_until",
            "recent_context",
            "last_updated_at",
        }
    )


def test_events_ingest_alias_returns_ack_shape():
    client = TestClient(app)
    client_message_id = f"contract-shape-msg-{uuid4()}"

    response = client.post(
        "/api/v1/events/ingest",
        json={
            "channel": "desktop_plugin",
            "message_type": "text",
            "text": "Need a quick checkpoint.",
            "client_message_id": client_message_id,
            "occurred_at": "2026-03-13T09:00:00+08:00",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["event_id"]
    assert body["accepted"] is True
    assert body["processing"] is True
    assert "state" in body
    assert "assistant_reply" in body
    assert "suggest_next_action" in body


def test_events_ingest_duplicate_returns_conflict():
    client = TestClient(app)
    client_message_id = f"contract-shape-msg-{uuid4()}"
    payload = {
        "channel": "desktop_plugin",
        "message_type": "text",
        "text": "Need a quick checkpoint.",
        "client_message_id": client_message_id,
        "occurred_at": "2026-03-13T09:00:00+08:00",
    }

    first = client.post("/api/v1/events/ingest", json=payload)
    second = client.post("/api/v1/events/ingest", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"] == "client_message_id already exists for this source"


def test_recommendation_next_alias_returns_pull_shape():
    client = TestClient(app)

    response = client.get("/api/v1/recommendations/next")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["recommendation_id"]
    assert body["mode"] == "pull"
    assert "items" in body
    assert "empty_state" in body


def test_top_level_brief_route_returns_contract_shape():
    client = TestClient(app)

    response = client.get("/api/v1/brief")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert set(body["summary"]).issuperset({"active_projects", "active_values", "urgent_nodes", "stale_nodes"})
    assert isinstance(body["items"], list)
