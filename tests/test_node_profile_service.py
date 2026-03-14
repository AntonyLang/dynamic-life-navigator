from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models.action_node import ActionNode
from app.schemas.parsing import NodeProfileDecisionDTO
from app.services.node_profile_service import compare_shadow_profile_decision


def _create_profiled_node() -> ActionNode:
    now = datetime.now(timezone.utc)
    return ActionNode(
        node_id=uuid4(),
        user_id="local-user",
        drive_type="project",
        status="active",
        title="Debug parser and write report",
        summary="Investigate the parser and write a concise report.",
        tags=["coding"],
        priority_score=50,
        dynamic_urgency_score=0,
        mental_energy_required=72,
        physical_energy_required=20,
        estimated_minutes=45,
        recommended_context_tags=["deep_focus"],
        confidence_level="medium",
        profiling_status="completed",
        profiled_at=now,
        ai_context={
            "profile_method": "deterministic_async_v2",
            "profile_signals": ["deep_focus_signal"],
            "profile_metadata": {
                "primary": {
                    "provider": "deterministic",
                    "profile_version": "deterministic_async_v2",
                }
            },
        },
        metadata_={},
        updated_at=now,
    )


def test_compare_shadow_profile_records_exact_match(monkeypatch):
    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")

    with SessionLocal() as session:
        node = _create_profiled_node()
        session.add(node)
        session.commit()

        try:
            monkeypatch.setattr(
                "app.services.node_profile_service.get_shadow_node_profile_provider",
                lambda: type(
                    "ExactProvider",
                    (),
                    {
                        "name": "gemini_direct",
                        "profile": lambda self, current_node: NodeProfileDecisionDTO.model_validate(
                            {
                                "status": "completed",
                                "node_id": str(current_node.node_id),
                                "profile": {
                                    "mental_energy_required": 72,
                                    "physical_energy_required": 20,
                                    "estimated_minutes": 45,
                                    "recommended_context_tags": ["deep_focus"],
                                    "confidence_level": "medium",
                                    "ai_context": {},
                                },
                                "metadata": {
                                    "provider": "gemini_direct",
                                    "profile_version": "gemini_direct_profile_v0",
                                },
                            }
                        ),
                    },
                )(),
            )

            result = compare_shadow_profile_decision(session, str(node.node_id))

            refreshed = session.get(ActionNode, node.node_id)
            assert result["comparison_result"] == "exact_match"
            assert refreshed is not None
            assert refreshed.ai_context["profile_comparison_result"] == "exact_match"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node.node_id))
            session.commit()


def test_compare_shadow_profile_records_compatible_match(monkeypatch):
    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")

    with SessionLocal() as session:
        node = _create_profiled_node()
        session.add(node)
        session.commit()

        try:
            monkeypatch.setattr(
                "app.services.node_profile_service.get_shadow_node_profile_provider",
                lambda: type(
                    "CompatibleProvider",
                    (),
                    {
                        "name": "gemini_direct",
                        "profile": lambda self, current_node: NodeProfileDecisionDTO.model_validate(
                            {
                                "status": "completed",
                                "node_id": str(current_node.node_id),
                                "profile": {
                                    "mental_energy_required": 75,
                                    "physical_energy_required": 18,
                                    "estimated_minutes": 50,
                                    "recommended_context_tags": ["deep_focus"],
                                    "confidence_level": "medium",
                                    "ai_context": {},
                                },
                                "metadata": {
                                    "provider": "gemini_direct",
                                    "profile_version": "gemini_direct_profile_v0",
                                },
                            }
                        ),
                    },
                )(),
            )

            result = compare_shadow_profile_decision(session, str(node.node_id))

            refreshed = session.get(ActionNode, node.node_id)
            assert result["comparison_result"] == "compatible_match"
            assert refreshed is not None
            assert refreshed.ai_context["profile_comparison_result"] == "compatible_match"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node.node_id))
            session.commit()


def test_compare_shadow_profile_records_shadow_failed(monkeypatch):
    monkeypatch.setenv("PROFILE_PROVIDER", "deterministic")
    monkeypatch.setenv("PROFILE_SHADOW_ENABLED", "true")
    monkeypatch.setenv("PROFILE_SHADOW_PROVIDER", "gemini_direct")

    with SessionLocal() as session:
        node = _create_profiled_node()
        session.add(node)
        session.commit()

        try:
            monkeypatch.setattr(
                "app.services.node_profile_service.get_shadow_node_profile_provider",
                lambda: type(
                    "FailedProvider",
                    (),
                    {
                        "name": "gemini_direct",
                        "profile": lambda self, current_node: NodeProfileDecisionDTO.model_validate(
                            {
                                "status": "completed",
                                "node_id": str(current_node.node_id),
                                "profile": {
                                    "mental_energy_required": 72,
                                    "physical_energy_required": 20,
                                    "estimated_minutes": 45,
                                    "recommended_context_tags": ["deep_focus"],
                                    "confidence_level": "medium",
                                    "ai_context": {},
                                },
                                "metadata": {
                                    "provider": "gemini_direct",
                                    "profile_version": "gemini_direct_profile_v0",
                                    "fallback_reason": "validation_error_fallback_after_2_attempts",
                                },
                            }
                        ),
                    },
                )(),
            )

            result = compare_shadow_profile_decision(session, str(node.node_id))

            refreshed = session.get(ActionNode, node.node_id)
            assert result["comparison_result"] == "shadow_failed"
            assert refreshed is not None
            assert refreshed.ai_context["profile_comparison_result"] == "shadow_failed"
        finally:
            session.execute(delete(ActionNode).where(ActionNode.node_id == node.node_id))
            session.commit()
