"""Gemini Developer API-backed structured node profiler with deterministic fallback."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.prompts.structured_node_profile_assets import (
    build_structured_node_profile_model_response_schema,
    build_structured_node_profile_request,
)
from app.schemas.parsing import NodeProfileDecisionDTO
from app.services.profile_provider import (
    DeterministicNodeProfileProvider,
    NodeProfileProvider,
)

if TYPE_CHECKING:
    from app.models.action_node import ActionNode

GEMINI_DIRECT_PROFILE_VERSION = "gemini_direct_profile_v0"


class GeminiDirectNodeProfileProvider:
    """Schema-first node profile provider using Gemini's generateContent API."""

    name = "gemini_direct"
    profile_version = GEMINI_DIRECT_PROFILE_VERSION

    def __init__(
        self,
        fallback_provider: NodeProfileProvider | None = None,
        *,
        api_key: str | None,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
    ) -> None:
        self._fallback_provider = fallback_provider or DeterministicNodeProfileProvider()
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds

    def build_request_artifacts(self, node: ActionNode) -> dict[str, object]:
        return build_structured_node_profile_request(node, self._model_name)

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
                "responseJsonSchema": build_structured_node_profile_model_response_schema(),
            },
        }

    def build_request_body(self, request_payload: dict[str, object]) -> bytes:
        return json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _post_generate_content_request(self, *, request_body: bytes) -> dict[str, Any]:
        with httpx.Client(timeout=self._timeout_seconds, trust_env=False) as client:
            response = client.post(
                f"{self._base_url}/models/{self._model_name}:generateContent",
                headers={
                    "x-goog-api-key": str(self._api_key),
                    "Content-Type": "application/json; charset=utf-8",
                },
                content=request_body,
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
        node: ActionNode,
        request_artifacts: dict[str, object],
    ) -> dict[str, Any]:
        normalized_payload = dict(candidate_payload)
        profile_payload = dict(normalized_payload.get("profile") or {})
        profile_payload["ai_context"] = {
            "profile_method": self.profile_version,
            "profile_provider": self.name,
        }
        normalized_payload["profile"] = profile_payload
        normalized_payload["node_id"] = str(node.node_id)
        normalized_payload["metadata"] = {
            "provider": self.name,
            "profile_version": self.profile_version,
            "prompt_version": request_artifacts["metadata"]["prompt_version"],
            "model_name": request_artifacts["metadata"]["model_name"],
            "fallback_reason": None,
        }
        return normalized_payload

    def _generate_candidate_payload(
        self,
        node: ActionNode,
        request_artifacts: dict[str, object],
        attempt: int,
    ) -> dict[str, Any]:
        del attempt
        request_payload = self.build_request_payload(request_artifacts)
        request_body = self.build_request_body(request_payload)
        response_payload = self._post_generate_content_request(request_body=request_body)

        output_text = self._extract_output_text(response_payload)
        if output_text is None:
            raise ValueError("empty_response_text")

        candidate_payload = json.loads(output_text)
        if not isinstance(candidate_payload, dict):
            raise ValueError("non_object_json_response")

        return self._normalize_candidate_payload(candidate_payload, node, request_artifacts)

    def profile(self, node: ActionNode) -> NodeProfileDecisionDTO:
        request_artifacts = self.build_request_artifacts(node)
        delegated = self._fallback_provider.profile(node)

        if not self._api_key:
            return NodeProfileDecisionDTO(
                status=delegated.status,
                node_id=delegated.node_id,
                profile=delegated.profile,
                metadata={
                    "provider": self.name,
                    "profile_version": self.profile_version,
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
                candidate_payload = self._generate_candidate_payload(node, request_artifacts, attempt)
                return NodeProfileDecisionDTO.model_validate(candidate_payload)
            except json.JSONDecodeError:
                last_error_reason = "invalid_json_response"
                last_error_detail = None
            except ValidationError:
                last_error_reason = "validation_error"
                last_error_detail = None
            except httpx.HTTPError as exc:
                last_error_reason = "request_error"
                last_error_detail = self._extract_http_error_detail(exc)
            except UnicodeError as exc:
                last_error_reason = "encoding_error"
                last_error_detail = f"{exc.__class__.__name__}: {exc}"[:300]
            except ValueError as exc:
                last_error_reason = str(exc)
                last_error_detail = None

        return NodeProfileDecisionDTO(
            status=delegated.status,
            node_id=delegated.node_id,
            profile=delegated.profile,
            metadata={
                "provider": self.name,
                "profile_version": self.profile_version,
                "prompt_version": str(request_artifacts["metadata"]["prompt_version"]),
                "model_name": str(request_artifacts["metadata"]["model_name"]),
                "fallback_reason": f"{last_error_reason}_fallback_after_{max_attempts}_attempts",
                "error_detail": last_error_detail,
            },
        )
