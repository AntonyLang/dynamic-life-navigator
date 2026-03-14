"use strict";

const DEFAULT_SERVER_ORIGIN = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 8000;
const CONFIG_KEYS = {
  serverOrigin: "dln.serverOrigin",
  authToken: "dln.authToken",
};

const launchListeners = new Set();
const memoryStorage = new Map();
let launchSequence = 0;
let currentLaunchContext = {
  code: "shell",
  type: "manual",
  payload: null,
  launchId: launchSequence,
};

function getUtools() {
  return globalThis.utools ?? null;
}

function getDbStorage() {
  return getUtools()?.dbStorage ?? null;
}

function getCryptoStorage() {
  return getUtools()?.dbCryptoStorage ?? null;
}

function readStoredValue(key, sensitive) {
  const storage = sensitive ? getCryptoStorage() : getDbStorage();
  if (storage && typeof storage.getItem === "function") {
    const value = storage.getItem(key);
    return typeof value === "string" ? value : null;
  }
  return memoryStorage.get(`${sensitive ? "secure" : "plain"}:${key}`) ?? null;
}

function writeStoredValue(key, value, sensitive) {
  const storage = sensitive ? getCryptoStorage() : getDbStorage();
  if (storage && typeof storage.setItem === "function") {
    storage.setItem(key, value);
    return;
  }
  memoryStorage.set(`${sensitive ? "secure" : "plain"}:${key}`, value);
}

function normalizeServerOrigin(value) {
  const trimmed = typeof value === "string" ? value.trim() : "";
  const candidate = trimmed || DEFAULT_SERVER_ORIGIN;
  return candidate.replace(/\/+$/, "");
}

function getConfig() {
  const authToken = readStoredValue(CONFIG_KEYS.authToken, true);
  return {
    serverOrigin: normalizeServerOrigin(readStoredValue(CONFIG_KEYS.serverOrigin, false)),
    authToken: authToken ? authToken : null,
  };
}

function saveConfig(nextConfig) {
  const config = {
    serverOrigin: normalizeServerOrigin(nextConfig?.serverOrigin),
    authToken: nextConfig?.authToken ? String(nextConfig.authToken).trim() : null,
  };

  writeStoredValue(CONFIG_KEYS.serverOrigin, config.serverOrigin, false);
  writeStoredValue(CONFIG_KEYS.authToken, config.authToken ?? "", true);
  return config;
}

function buildRequestHeaders(authToken) {
  const headers = {
    "Content-Type": "application/json",
  };

  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }

  return headers;
}

function createBridgeError(message, options = {}) {
  return {
    name: "DlnBridgeError",
    message,
    status: options.status ?? 0,
    requestId: options.requestId ?? null,
    code: options.code ?? "request_error",
    detail: options.detail ?? null,
  };
}

async function readJsonSafely(response) {
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

async function request(path, init = {}) {
  const { serverOrigin, authToken } = getConfig();
  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const url = new URL(path, serverOrigin).toString();

  try {
    const response = await fetch(url, {
      method: init.method ?? "GET",
      headers: {
        ...buildRequestHeaders(authToken),
        ...(init.headers ?? {}),
      },
      body: init.body ? JSON.stringify(init.body) : undefined,
      signal: controller.signal,
    });
    const requestId = response.headers.get("X-Request-Id");
    const body = await readJsonSafely(response);

    if (!response.ok) {
      const detail = body && typeof body === "object" && "detail" in body ? body.detail : null;
      throw createBridgeError(
        typeof detail === "string" ? detail : `Request failed with status ${response.status}.`,
        {
          status: response.status,
          requestId,
          code: response.status === 409 ? "duplicate_message" : response.status >= 500 ? "server_error" : "request_error",
          detail,
        },
      );
    }

    return {
      data: body,
      requestId,
    };
  } catch (error) {
    if (error && typeof error === "object" && error.name === "DlnBridgeError") {
      throw error;
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw createBridgeError("Request timed out.", {
        code: "timeout",
      });
    }

    throw createBridgeError("Network request failed.", {
      code: "network_error",
      detail: error,
    });
  } finally {
    clearTimeout(timeoutHandle);
  }
}

function normalizeLaunchContext(action) {
  launchSequence += 1;
  return {
    code: action?.code === "pull" || action?.code === "brief" ? action.code : "shell",
    type: typeof action?.type === "string" ? action.type : "manual",
    payload: action?.payload ?? null,
    launchId: launchSequence,
  };
}

function publishLaunchContext(action) {
  currentLaunchContext = normalizeLaunchContext(action);
  for (const listener of launchListeners) {
    listener(currentLaunchContext);
  }
}

function registerUtoolsEventHooks() {
  const utools = getUtools();
  if (!utools || typeof utools.onPluginEnter !== "function") {
    return;
  }

  utools.onPluginEnter((action) => {
    publishLaunchContext(action);
  });
}

function createBridge() {
  return {
    getLaunchContext() {
      return currentLaunchContext;
    },
    subscribeLaunchContext(listener) {
      launchListeners.add(listener);
      return () => {
        launchListeners.delete(listener);
      };
    },
    getState() {
      return request("/api/v1/state");
    },
    sendChatMessage(payload) {
      return request("/api/v1/chat/messages", {
        method: "POST",
        body: payload,
      });
    },
    pullRecommendation(options = {}) {
      const limit = typeof options.limit === "number" ? options.limit : 2;
      return request(`/api/v1/recommendations/next?limit=${limit}`);
    },
    getBrief() {
      return request("/api/v1/brief");
    },
    submitFeedback(recommendationId, payload) {
      return request(`/api/v1/recommendations/${recommendationId}/feedback`, {
        method: "POST",
        body: payload,
      });
    },
    async getConfig() {
      return getConfig();
    },
    async saveConfig(config) {
      return saveConfig(config);
    },
    async pingBackend() {
      const startedAt = Date.now();
      const result = await request("/health");
      return {
        ok: true,
        responseTimeMs: Date.now() - startedAt,
        status: 200,
        body: result.data,
      };
    },
  };
}

const bridge = createBridge();
registerUtoolsEventHooks();

if (typeof window !== "undefined") {
  window.dlnBridge = bridge;
}

module.exports = {
  REQUEST_TIMEOUT_MS,
  DEFAULT_SERVER_ORIGIN,
  createBridge,
  bridge,
  __private: {
    getConfig,
    saveConfig,
    request,
    normalizeLaunchContext,
    publishLaunchContext,
    resetLaunchContext() {
      launchSequence = 0;
      currentLaunchContext = {
        code: "shell",
        type: "manual",
        payload: null,
        launchId: launchSequence,
      };
      launchListeners.clear();
      memoryStorage.clear();
    },
  },
};
