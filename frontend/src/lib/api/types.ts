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

export interface StateResetRequest {
  mental_energy: number;
  physical_energy: number;
  reason: string;
}

export interface StateResetResponse {
  request_id: string;
  state: UserStateSnapshot;
  reset_reason: string;
  updated_at: string;
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

export type RecommendationFeedbackType = "accepted" | "ignored" | "dismissed" | "rejected" | "snoozed";

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

export type DriveType = "project" | "value";

export interface ActionNodeCreateRequest {
  drive_type: DriveType;
  title: string;
  summary?: string | null;
  tags: string[];
  priority_score?: number | null;
  dynamic_urgency_score?: number | null;
  estimated_minutes?: number | null;
  ddl_timestamp?: string | null;
}

export interface ActionNodeResponse {
  node_id: string;
  drive_type: string;
  status: string;
  title: string;
  summary: string | null;
  tags: string[];
  priority_score: number;
  dynamic_urgency_score: number;
  mental_energy_required: number;
  physical_energy_required: number;
  estimated_minutes: number | null;
  recommended_context_tags: string[];
  confidence_level: string;
  profiling_status: string;
  profiled_at: string | null;
}

export interface ActionNodeCreateResponse {
  request_id: string;
  accepted: boolean;
  profiling_enqueued: boolean;
  node: ActionNodeResponse;
}

export interface ApiSuccess<T> {
  data: T;
  requestId: string | null;
}

export class ApiError extends Error {
  status: number;
  requestId: string | null;
  code: string;
  detail: unknown;

  constructor(message: string, options: { status: number; requestId: string | null; code: string; detail: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.requestId = options.requestId;
    this.code = options.code;
    this.detail = options.detail;
  }
}
