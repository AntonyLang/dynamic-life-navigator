"""Small local helper to debug Gemini direct parser requests end to end."""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import get_settings
from app.services.gemini_direct_parser import GeminiDirectEventParserProvider
from app.services.parser_provider import DeterministicEventParserProvider


def build_event(text: str) -> SimpleNamespace:
    settings = get_settings()
    return SimpleNamespace(
        event_id=uuid4(),
        user_id=settings.default_user_id,
        source="frontend_web_shell",
        source_event_type="text",
        external_event_id=f"debug-{uuid4()}",
        payload_hash=f"debug-hash-{uuid4()}",
        raw_text=text,
        raw_payload={},
        occurred_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="Raw text to send through the Gemini direct parser")
    args = parser.parse_args()

    settings = get_settings()
    provider = GeminiDirectEventParserProvider(
        DeterministicEventParserProvider(),
        api_key=settings.gemini_api_key,
        base_url=settings.gemini_base_url,
        model_name=settings.structured_parser_model_name,
        timeout_seconds=settings.structured_parser_timeout_seconds,
    )

    event = build_event(args.text)
    artifacts = provider.build_request_artifacts(event)
    payload = provider.build_request_payload(artifacts)
    body = provider.build_request_body(payload)

    print("Provider:", provider.name)
    print("Model:", settings.structured_parser_model_name)
    print("Base URL:", settings.gemini_base_url)
    print("Has API key:", bool(settings.gemini_api_key))
    print("Body bytes:", len(body))
    print("Body preview:")
    print(body.decode("utf-8")[:1200])

    try:
        response_payload = provider._post_generate_content_request(payload)
        print("\nRaw response:")
        print(json.dumps(response_payload, ensure_ascii=False, indent=2)[:3000])
    except Exception:
        print("\nRequest raised exception:")
        traceback.print_exc()
        return 1

    try:
        decision = provider.parse(event)
    except Exception:
        print("\nProvider parse raised exception:")
        traceback.print_exc()
        return 1

    print("\nValidated decision:")
    print(decision.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
