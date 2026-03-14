from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.action_node import ActionNode
from app.schemas.parsing import NodeProfileDecisionDTO
from app.services.gemini_direct_profile import GeminiDirectNodeProfileProvider
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


def test_create_action_node_applies_chinese_light_admin_prefill():
    client = TestClient(app)

    response = client.post(
        "/api/v1/nodes",
        json={
            "drive_type": "project",
            "title": "\u6574\u7406\u90ae\u7bb1\u5f52\u6863",
            "tags": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    node_id = UUID(body["node"]["node_id"])

    with SessionLocal() as session:
        try:
            node = session.scalar(select(ActionNode).where(ActionNode.node_id == node_id))
            assert node is not None
            assert node.mental_energy_required <= 35
            assert node.physical_energy_required >= 30
            assert "light_admin" in node.recommended_context_tags
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
            assert node.ai_context["profile_method"] == "deterministic_async_v2"
            assert node.ai_context["profile_metadata"]["primary"]["provider"] == "deterministic"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()


def test_profile_action_node_supports_chinese_deep_focus_hint():
    client = TestClient(app)

    response = client.post(
        "/api/v1/nodes",
        json={
            "drive_type": "project",
            "title": "\u8c03\u8bd5 parser \u5e76\u5199\u62a5\u544a",
            "summary": "\u68c0\u67e5\u5931\u8d25\u6a21\u5f0f\uff0c\u5b8c\u6210\u8c03\u8bd5\uff0c\u518d\u5199\u4e00\u4efd\u7b80\u77ed\u62a5\u544a\u3002",
            "tags": [],
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
            assert node.mental_energy_required >= 72
            assert node.estimated_minutes >= 45
            assert "deep_focus" in node.recommended_context_tags
            assert "cognitive_work_signal" in node.ai_context["profile_signals"]
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()


def test_profile_action_node_records_shadow_drift_without_overwriting_primary_fields(monkeypatch):
    client = TestClient(app)

    response = client.post(
        "/api/v1/nodes",
        json={
            "drive_type": "project",
            "title": "Debug parser and prepare report",
            "summary": "Investigate the parser and write a concise report.",
            "tags": ["coding"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    node_id = UUID(body["node"]["node_id"])

    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")
    get_settings.cache_clear()
    monkeypatch.setattr(
        GeminiDirectNodeProfileProvider,
        "profile",
        lambda self, node: NodeProfileDecisionDTO.model_validate(
            {
                "status": "completed",
                "node_id": str(node.node_id),
                "profile": {
                    "mental_energy_required": 30,
                    "physical_energy_required": 30,
                    "estimated_minutes": 25,
                    "recommended_context_tags": ["light_admin"],
                    "confidence_level": "medium",
                    "ai_context": {
                        "profile_method": "gemini_direct_profile_v0",
                        "profile_provider": "gemini_direct",
                    },
                },
                "metadata": {
                    "provider": "gemini_direct",
                    "profile_version": "gemini_direct_profile_v0",
                    "prompt_version": "structured_node_profile_prompt_v1",
                    "model_name": "gemini-2.5-flash",
                },
            }
        ),
    )

    with SessionLocal() as session:
        try:
            result = profile_action_node(session, str(node_id))
            assert result["status"] == "completed"

            node = session.get(ActionNode, node_id)
            assert node is not None
            assert node.profiling_status == "completed"
            assert node.mental_energy_required >= 70
            assert "deep_focus" in node.recommended_context_tags
            assert node.ai_context["profile_metadata"]["primary"]["provider"] == "deterministic"
            assert node.ai_context["profile_metadata"]["shadow"]["shadow_provider"] == "gemini_direct"
            assert node.ai_context["profile_comparison_result"] == "drift"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node_id))
            session.commit()
            get_settings.cache_clear()
