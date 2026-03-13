from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.action_node import ActionNode
from app.services.node_profile_service import profile_action_node

settings = get_settings()


def test_create_action_node_uses_conservative_defaults():
    client = TestClient(app)

    response = client.post(
        "/api/v1/nodes",
        json={
            "drive_type": "project",
            "title": "New node without explicit profile",
            "tags": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    node_id = UUID(body["node"]["node_id"])

    with SessionLocal() as session:
        try:
            node = session.get(ActionNode, node_id)
            assert node is not None
            assert body["accepted"] is True
            assert body["profiling_enqueued"] is False
            assert node.mental_energy_required == 50
            assert node.physical_energy_required == 20
            assert node.estimated_minutes == 30
            assert node.confidence_level == "low"
            assert node.profiling_status == "pending"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()


def test_create_action_node_applies_heuristic_prefill():
    client = TestClient(app)

    response = client.post(
        "/api/v1/nodes",
        json={
            "drive_type": "project",
            "title": "Debug the failing parser",
            "tags": ["coding", "debug"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    node_id = UUID(body["node"]["node_id"])

    with SessionLocal() as session:
        try:
            node = session.scalar(select(ActionNode).where(ActionNode.node_id == node_id))
            assert node is not None
            assert node.mental_energy_required >= 70
            assert "deep_focus" in node.recommended_context_tags
            assert node.profiling_status == "pending"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()


def test_profile_action_node_completes_async_backfill():
    client = TestClient(app)

    response = client.post(
        "/api/v1/nodes",
        json={
            "drive_type": "project",
            "title": "Prepare review report for parser regression",
            "summary": "Review the failure modes, summarize the incident, and propose the next patch plan.",
            "tags": ["coding"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    node_id = UUID(body["node"]["node_id"])

    with SessionLocal() as session:
        try:
            result = profile_action_node(session, str(node_id))
            assert result["status"] == "completed"

            node = session.get(ActionNode, node_id)
            assert node is not None
            assert node.profiling_status == "completed"
            assert node.profiled_at is not None
            assert node.confidence_level == "medium"
            assert node.mental_energy_required >= 70
            assert node.estimated_minutes >= 45
            assert "deep_focus" in node.recommended_context_tags
            assert node.ai_context["profile_method"] == "deterministic_async_v1"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()
