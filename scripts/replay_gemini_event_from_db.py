"""Replay one persisted event through the Gemini parser provider from the CLI.

This is useful when the live app path fails but we want to compare the exact
stored `event_logs` input in a standalone process.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.gemini_direct_parser import GeminiDirectEventParserProvider
from app.services.parser_provider import DeterministicEventParserProvider


def load_event(event_id: str) -> SimpleNamespace:
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                select
                    event_id,
                    user_id,
                    source,
                    source_event_type,
                    external_event_id,
                    payload_hash,
                    raw_text,
                    raw_payload,
                    occurred_at,
                    ingested_at
                from event_logs
                where event_id = :event_id
                """
            ),
            {"event_id": str(UUID(event_id))},
        ).mappings().one()

    return SimpleNamespace(
        event_id=row["event_id"],
        user_id=row["user_id"],
        source=row["source"],
        source_event_type=row["source_event_type"],
        external_event_id=row["external_event_id"],
        payload_hash=row["payload_hash"],
        raw_text=row["raw_text"],
        raw_payload=row["raw_payload"] or {},
        occurred_at=row["occurred_at"],
        ingested_at=row["ingested_at"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id", help="Persisted event_id to replay through Gemini")
    args = parser.parse_args()

    settings = get_settings()
    provider = GeminiDirectEventParserProvider(
        DeterministicEventParserProvider(),
        api_key=settings.gemini_api_key,
        base_url=settings.gemini_base_url,
        model_name=settings.structured_parser_model_name,
        timeout_seconds=settings.structured_parser_timeout_seconds,
    )
    event = load_event(args.event_id)
    request_artifacts = provider.build_request_artifacts(event)
    request_payload = provider.build_request_payload(request_artifacts)
    request_body = provider.build_request_body(request_payload)
    decision = provider.parse(event)

    print("Provider:", provider.name)
    print("Model:", settings.structured_parser_model_name)
    print("Event ID:", event.event_id)
    print("Source:", event.source)
    print("Raw text:", event.raw_text)
    print("Raw payload:", json.dumps(event.raw_payload, ensure_ascii=False)[:500])
    print("Body bytes:", len(request_body))
    print("Decision:")
    print(decision.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
