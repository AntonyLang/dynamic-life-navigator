import type {
  BridgeConfig,
  BridgeSuccess,
  ChatMessageRequest,
  ChatMessageResponse,
  DlnBridge,
  DlnBridgeErrorShape,
  LaunchContext,
  PingBackendResult,
  RecommendationBriefResponse,
  RecommendationFeedbackRequest,
  RecommendationFeedbackResponse,
  RecommendationPullResponse,
  StateResponse,
} from "./types";

const FALLBACK_LAUNCH_CONTEXT: LaunchContext = {
  code: "shell",
  type: "manual",
  payload: null,
  launchId: 0,
};

const FALLBACK_CONFIG: BridgeConfig = {
  serverOrigin: "http://127.0.0.1:8000",
  authToken: null,
};

export class BridgeError extends Error {
  status: number;
  requestId: string | null;
  code: string;
  detail: unknown;

  constructor(message: string, options?: DlnBridgeErrorShape) {
    super(message);
    this.name = "BridgeError";
    this.status = options?.status ?? 0;
    this.requestId = options?.requestId ?? null;
    this.code = options?.code ?? "request_error";
    this.detail = options?.detail ?? null;
  }
}

function getBridge(): DlnBridge {
  if (!window.dlnBridge) {
    throw new BridgeError("uTools bridge is unavailable.", {
      code: "bridge_unavailable",
    });
  }
  return window.dlnBridge;
}

function normalizeError(error: unknown): BridgeError {
  if (error instanceof BridgeError) {
    return error;
  }

  if (error && typeof error === "object") {
    const shape = error as DlnBridgeErrorShape;
    return new BridgeError(shape.message ?? "Request failed.", shape);
  }

  if (error instanceof Error) {
    return new BridgeError(error.message, {
      detail: error,
    });
  }

  return new BridgeError("Request failed.");
}

async function runRequest<T>(runner: () => Promise<BridgeSuccess<T>>): Promise<BridgeSuccess<T>> {
  try {
    return await runner();
  } catch (error) {
    throw normalizeError(error);
  }
}

export const bridgeClient = {
  getLaunchContext(): LaunchContext {
    try {
      return getBridge().getLaunchContext();
    } catch {
      return FALLBACK_LAUNCH_CONTEXT;
    }
  },
  subscribeLaunchContext(listener: (context: LaunchContext) => void) {
    try {
      return getBridge().subscribeLaunchContext?.(listener);
    } catch {
      return undefined;
    }
  },
  getState() {
    return runRequest<StateResponse>(() => getBridge().getState());
  },
  sendChatMessage(payload: ChatMessageRequest) {
    return runRequest<ChatMessageResponse>(() => getBridge().sendChatMessage(payload));
  },
  pullRecommendation(limit = 2) {
    return runRequest<RecommendationPullResponse>(() => getBridge().pullRecommendation({ limit }));
  },
  getBrief() {
    return runRequest<RecommendationBriefResponse>(() => getBridge().getBrief());
  },
  submitFeedback(recommendationId: string, payload: RecommendationFeedbackRequest) {
    return runRequest<RecommendationFeedbackResponse>(() => getBridge().submitFeedback(recommendationId, payload));
  },
  async getConfig() {
    try {
      return await getBridge().getConfig();
    } catch {
      return FALLBACK_CONFIG;
    }
  },
  async saveConfig(config: BridgeConfig) {
    return getBridge().saveConfig(config);
  },
  async pingBackend(): Promise<PingBackendResult> {
    return getBridge().pingBackend();
  },
};
