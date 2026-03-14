export interface UserStateSnapshot {
  mental_energy: number;
  physical_energy: number;
  focus_mode: string;
  do_not_disturb_until: string | null;
  recent_context: string | null;
  last_updated_at: string | null;
}

export interface StateResponse {
  request_id: string;
  state: UserStateSnapshot;
}

export interface ChatMessageRequest {
  channel: string;
  message_type: string;
  text: string;
  client_message_id: string;
  occurred_at: string;
}

export interface ChatMessageResponse {
  request_id: string;
  event_id: string;
  state: UserStateSnapshot;
  assistant_reply: string;
  suggest_next_action: boolean;
  accepted: boolean;
  processing: boolean;
}

export interface RecommendationItem {
  node_id: string;
  title: string;
  message: string;
  reason_tags: string[];
}

export interface RecommendationPullResponse {
  request_id: string;
  recommendation_id: string;
  mode: "pull";
  items: RecommendationItem[];
  empty_state: boolean;
  fallback_message: string | null;
}

export interface RecommendationBriefSummary {
  active_projects: number;
  active_values: number;
  urgent_nodes: number;
  stale_nodes: number;
}

export interface RecommendationBriefItem {
  node_id: string;
  title: string;
  status: string;
  health: string;
  next_hint: string;
}

export interface RecommendationBriefResponse {
  request_id: string;
  summary: RecommendationBriefSummary;
  items: RecommendationBriefItem[];
}

export type RecommendationFeedbackType = "accepted" | "dismissed" | "snoozed";

export interface RecommendationFeedbackRequest {
  feedback: RecommendationFeedbackType;
  node_id?: string | null;
  channel?: string | null;
}

export interface RecommendationFeedbackResponse {
  request_id: string;
  recommendation_id: string;
  accepted: boolean;
  feedback: string;
}

export interface BridgeSuccess<T> {
  data: T;
  requestId: string | null;
}

export interface BridgeConfig {
  serverOrigin: string;
  authToken: string | null;
}

export interface PingBackendResult {
  ok: boolean;
  responseTimeMs: number;
  status: number;
  body: unknown;
}

export interface LaunchContext {
  code: "shell" | "pull" | "brief";
  type: string;
  payload: unknown;
  launchId: number;
}

export interface DlnBridgeErrorShape {
  name?: string;
  message?: string;
  status?: number;
  requestId?: string | null;
  code?: string;
  detail?: unknown;
}

export interface DlnBridge {
  getLaunchContext: () => LaunchContext;
  subscribeLaunchContext?: (listener: (context: LaunchContext) => void) => (() => void) | void;
  getState: () => Promise<BridgeSuccess<StateResponse>>;
  sendChatMessage: (payload: ChatMessageRequest) => Promise<BridgeSuccess<ChatMessageResponse>>;
  pullRecommendation: (options?: { limit?: number }) => Promise<BridgeSuccess<RecommendationPullResponse>>;
  getBrief: () => Promise<BridgeSuccess<RecommendationBriefResponse>>;
  submitFeedback: (
    recommendationId: string,
    payload: RecommendationFeedbackRequest,
  ) => Promise<BridgeSuccess<RecommendationFeedbackResponse>>;
  getConfig: () => Promise<BridgeConfig>;
  saveConfig: (config: BridgeConfig) => Promise<BridgeConfig>;
  pingBackend: () => Promise<PingBackendResult>;
}

export type TimelineEntry =
  | {
      id: string;
      kind: "user";
      text: string;
      status: "sending" | "processing" | "synced" | "failed";
      errorMessage?: string;
    }
  | {
      id: string;
      kind: "assistant";
      text: string;
      requestId?: string | null;
      eventId?: string;
    }
  | {
      id: string;
      kind: "system";
      text: string;
      tone: "info" | "error";
    }
  | {
      id: string;
      kind: "recommendation";
      recommendationId: string;
      emptyState: boolean;
      items: RecommendationItem[];
      fallbackMessage: string | null;
      status: "loading" | "ready" | "empty" | "load_failed" | "feedback_submitting" | "feedback_done" | "feedback_failed";
      errorMessage?: string;
    };
