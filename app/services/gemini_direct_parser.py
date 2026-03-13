"""Gemini Developer API-backed structured parser with deterministic fallback."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.models.event_log import EventLog
from app.prompts.structured_event_parser_assets import (
    build_structured_event_parser_model_response_schema,
    build_structured_event_parser_request,
)
from app.schemas.parsing import ParserDecisionDTO
from app.services.parser_provider import (
    DeterministicEventParserProvider,
    EventParserProvider,
)

GEMINI_DIRECT_PARSER_VERSION = "gemini_direct_v0"


class GeminiDirectEventParserProvider:
    """Schema-first parser provider using Gemini's generateContent API."""

    name = "gemini_direct"
    parser_version = GEMINI_DIRECT_PARSER_VERSION

    def __init__(
        self,
        fallback_provider: EventParserProvider | None = None,
        *,
        api_key: str | None,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
    ) -> None:
        self._fallback_provider = fallback_provider or DeterministicEventParserProvider()
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds

    def build_request_artifacts(self, event: EventLog) -> dict[str, object]:
        return build_structured_event_parser_request(event, self._model_name)

    def build_request_payload(self, request_artifacts: dict[str, object]) -> dict[str, object]:
        return {
            "systemInstruction": {
                "parts": [{"text": request_artifacts["system_prompt"]}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": request_artifacts["user_prompt"]}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": build_structured_event_parser_model_response_schema(),
            },
        }

    def _post_generate_content_request(self, request_payload: dict[str, object]) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/models/{self._model_name}:generateContent",
            headers={
                "x-goog-api-key": str(self._api_key),
                "Content-Type": "application/json",
            },
            json=request_payload,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _extract_http_error_detail(self, exc: httpx.HTTPError) -> str:
        response = getattr(exc, "response", None)
        if response is None:
            return exc.__class__.__name__
        try:
            body = response.text.strip()
        except Exception:
            body = ""
        detail = body or response.reason_phrase or exc.__class__.__name__
        detail = detail.replace("\n", " ").replace("\r", " ")
        return detail[:300]

    def _extract_output_text(self, response_payload: dict[str, Any]) -> str | None:
        candidates = response_payload.get("candidates")
        if not isinstance(candidates, list):
            return None

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
        return None

    def _normalize_candidate_payload(
        self,
        candidate_payload: dict[str, Any],
        request_artifacts: dict[str, object],
    ) -> dict[str, Any]:
        normalized_payload = dict(candidate_payload)
        normalized_payload["metadata"] = {
            "provider": self.name,
            "parser_version": self.parser_version,
            "prompt_version": request_artifacts["metadata"]["prompt_version"],
            "model_name": request_artifacts["metadata"]["model_name"],
            "fallback_reason": None,
        }
        return normalized_payload

    def _generate_candidate_payload(
        self,
        request_artifacts: dict[str, object],
        attempt: int,
    ) -> dict[str, Any]:
        del attempt
        response_payload = self._post_generate_content_request(self.build_request_payload(request_artifacts))
        output_text = self._extract_output_text(response_payload)
        if output_text is None:
            raise ValueError("empty_response_text")

        candidate_payload = json.loads(output_text)
        if not isinstance(candidate_payload, dict):
            raise ValueError("non_object_json_response")

        return self._normalize_candidate_payload(candidate_payload, request_artifacts)

    def parse(self, event: EventLog) -> ParserDecisionDTO:
        request_artifacts = self.build_request_artifacts(event)
        delegated = self._fallback_provider.parse(event)

        if not self._api_key:
            return ParserDecisionDTO(
                status=delegated.status,
                impact=delegated.impact,
                metadata={
                    "provider": self.name,
                    "parser_version": self.parser_version,
                    "prompt_version": str(request_artifacts["metadata"]["prompt_version"]),
                    "model_name": str(request_artifacts["metadata"]["model_name"]),
                    "fallback_reason": "missing_gemini_api_key",
                },
            )

        max_attempts = get_settings().structured_parser_validation_retries + 1
        last_error_reason = "unknown_error"
        last_error_detail: str | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                candidate_payload = self._generate_candidate_payload(request_artifacts, attempt)
                return ParserDecisionDTO.model_validate(candidate_payload)
            except json.JSONDecodeError:
                last_error_reason = "invalid_json_response"
                last_error_detail = None
            except ValidationError:
                last_error_reason = "validation_error"
                last_error_detail = None
            except httpx.HTTPError as exc:
                last_error_reason = "request_error"
                last_error_detail = self._extract_http_error_detail(exc)
            except ValueError as exc:
                last_error_reason = str(exc)
                last_error_detail = None

        return ParserDecisionDTO(
            status=delegated.status,
            impact=delegated.impact,
            metadata={
                "provider": self.name,
                "parser_version": self.parser_version,
                "prompt_version": str(request_artifacts["metadata"]["prompt_version"]),
                "model_name": str(request_artifacts["metadata"]["model_name"]),
                "fallback_reason": f"{last_error_reason}_fallback_after_{max_attempts}_attempts",
                "error_detail": last_error_detail,
            },
        )
