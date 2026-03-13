"""OpenAI Responses-backed structured parser with deterministic fallback."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from app.models.event_log import EventLog
from app.prompts.structured_event_parser_assets import (
    build_structured_event_parser_request,
)
from app.schemas.parsing import ParserDecisionDTO
from app.services.parser_provider import (
    DeterministicEventParserProvider,
    EventParserProvider,
)

OPENAI_RESPONSES_PARSER_VERSION = "openai_responses_v0"


class OpenAIResponsesEventParserProvider:
    """Schema-first parser provider backed by the OpenAI Responses API.

    The provider is opt-in and always falls back to the deterministic parser if
    no API key is configured, the request fails, or the returned JSON cannot be
    validated.
    """

    name = "openai_responses"
    parser_version = OPENAI_RESPONSES_PARSER_VERSION

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
            "model": request_artifacts["metadata"]["model_name"],
            "instructions": request_artifacts["system_prompt"],
            "input": request_artifacts["user_prompt"],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "event_parser_decision",
                    "schema": request_artifacts["response_schema"],
                    "strict": True,
                }
            },
        }

    def _post_responses_request(self, request_payload: dict[str, object]) -> dict[str, Any]:
        response = httpx.post(
            f"{self._base_url}/responses",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _extract_output_text(self, response_payload: dict[str, Any]) -> str | None:
        output_text = response_payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        output = response_payload.get("output")
        if not isinstance(output, list):
            return None

        for item in output:
            if not isinstance(item, dict):
                continue

            for key in ("output_text", "text"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate

            content = item.get("content")
            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue

                text_candidate = block.get("text")
                if isinstance(text_candidate, str) and text_candidate.strip():
                    return text_candidate
                if isinstance(text_candidate, dict):
                    nested = text_candidate.get("value") or text_candidate.get("text")
                    if isinstance(nested, str) and nested.strip():
                        return nested

                for key in ("output_text", "json"):
                    candidate = block.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate

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
        response_payload = self._post_responses_request(self.build_request_payload(request_artifacts))
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
                    "fallback_reason": "missing_openai_api_key",
                },
            )

        max_attempts = 1
        from app.core.config import get_settings

        max_attempts = get_settings().structured_parser_validation_retries + 1
        last_error_reason = "unknown_error"

        for attempt in range(1, max_attempts + 1):
            try:
                candidate_payload = self._generate_candidate_payload(request_artifacts, attempt)
                return ParserDecisionDTO.model_validate(candidate_payload)
            except json.JSONDecodeError:
                last_error_reason = "invalid_json_response"
            except ValidationError:
                last_error_reason = "validation_error"
            except httpx.HTTPError:
                last_error_reason = "request_error"
            except ValueError as exc:
                last_error_reason = str(exc)

        return ParserDecisionDTO(
            status=delegated.status,
            impact=delegated.impact,
            metadata={
                "provider": self.name,
                "parser_version": self.parser_version,
                "prompt_version": str(request_artifacts["metadata"]["prompt_version"]),
                "model_name": str(request_artifacts["metadata"]["model_name"]),
                "fallback_reason": f"{last_error_reason}_fallback_after_{max_attempts}_attempts",
            },
        )
