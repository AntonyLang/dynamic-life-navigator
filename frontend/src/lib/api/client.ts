import type {
  ActionNodeCreateRequest,
  ActionNodeCreateResponse,
  ApiSuccess,
  ChatMessageRequest,
  ChatMessageResponse,
  RecommendationBriefResponse,
  RecommendationFeedbackRequest,
  RecommendationFeedbackResponse,
  RecommendationPullResponse,
  StateResetRequest,
  StateResetResponse,
  StateResponse,
} from "./types";
import { ApiError } from "./types";

const DEFAULT_TIMEOUT_MS = 8000;

async function readJsonSafely(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  try {
    return await response.json();
  } catch {
    return null;
  }
}

function mapApiError(response: Response, body: unknown, requestId: string | null): ApiError {
  const detail =
    body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;

  if (response.status === 409) {
    return new ApiError("Message was already submitted.", {
      status: response.status,
      requestId,
      code: "duplicate_message",
      detail,
    });
  }

  return new ApiError(typeof detail === "string" ? detail : `Request failed with status ${response.status}.`, {
    status: response.status,
    requestId,
    code: response.status >= 500 ? "server_error" : "request_error",
    detail,
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiSuccess<T>> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
    });
  } catch (error) {
    window.clearTimeout(timeout);
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Request timed out.", {
        status: 0,
        requestId: null,
        code: "timeout",
        detail: null,
      });
    }

    throw new ApiError("Network request failed.", {
      status: 0,
      requestId: null,
      code: "network_error",
      detail: error,
    });
  }

  window.clearTimeout(timeout);
  const requestId = response.headers.get("X-Request-Id");
  const body = await readJsonSafely(response);

  if (!response.ok) {
    throw mapApiError(response, body, requestId);
  }

  return {
    data: body as T,
    requestId,
  };
}

export const apiClient = {
  getState: () => request<StateResponse>("/api/v1/state"),
  sendChatMessage: (payload: ChatMessageRequest) =>
    request<ChatMessageResponse>("/api/v1/chat/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  pullRecommendation: (limit = 2) =>
    request<RecommendationPullResponse>(`/api/v1/recommendations/next?limit=${limit}`),
  getBrief: () => request<RecommendationBriefResponse>("/api/v1/brief"),
  submitFeedback: (recommendationId: string, payload: RecommendationFeedbackRequest) =>
    request<RecommendationFeedbackResponse>(`/api/v1/recommendations/${recommendationId}/feedback`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  resetState: (payload: StateResetRequest) =>
    request<StateResetResponse>("/api/v1/state/reset", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createNode: (payload: ActionNodeCreateRequest) =>
    request<ActionNodeCreateResponse>("/api/v1/nodes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
