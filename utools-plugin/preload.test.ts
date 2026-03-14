/** @vitest-environment node */

import { createRequire } from "node:module";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const require = createRequire(import.meta.url);

function loadPreloadModule() {
  const modulePath = require.resolve("./preload.js");
  delete require.cache[modulePath];
  return require(modulePath) as {
    REQUEST_TIMEOUT_MS: number;
    createBridge: () => {
      getConfig: () => Promise<{ serverOrigin: string; authToken: string | null }>;
      saveConfig: (config: { serverOrigin: string; authToken: string | null }) => Promise<{
        serverOrigin: string;
        authToken: string | null;
      }>;
      sendChatMessage: (payload: unknown) => Promise<unknown>;
      pingBackend: () => Promise<unknown>;
    };
    __private: {
      resetLaunchContext: () => void;
    };
  };
}

function createHeaders(contentType = "application/json", requestId: string | null = null) {
  return {
    get(name: string) {
      if (name.toLowerCase() === "content-type") {
        return contentType;
      }
      if (name.toLowerCase() === "x-request-id") {
        return requestId;
      }
      return null;
    },
  };
}

describe("preload bridge", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as { utools?: unknown }).utools = {
      dbStorage: {
        storage: new Map<string, string>(),
        getItem(key: string) {
          return this.storage.get(key) ?? null;
        },
        setItem(key: string, value: string) {
          this.storage.set(key, value);
        },
      },
      dbCryptoStorage: {
        storage: new Map<string, string>(),
        getItem(key: string) {
          return this.storage.get(key) ?? null;
        },
        setItem(key: string, value: string) {
          this.storage.set(key, value);
        },
      },
      onPluginEnter: vi.fn(),
    };
  });

  afterEach(() => {
    delete (globalThis as { utools?: unknown }).utools;
  });

  it("persists server origin in dbStorage and token in dbCryptoStorage", async () => {
    const preload = loadPreloadModule();
    preload.__private.resetLaunchContext();
    const bridge = preload.createBridge();

    await bridge.saveConfig({
      serverOrigin: "http://example.com///",
      authToken: " secret-token ",
    });
    const config = await bridge.getConfig();

    expect(config).toEqual({
      serverOrigin: "http://example.com",
      authToken: "secret-token",
    });
    const utools = globalThis.utools as {
      dbStorage: { storage: Map<string, string> };
      dbCryptoStorage: { storage: Map<string, string> };
    };
    expect(utools.dbStorage.storage.get("dln.serverOrigin")).toBe("http://example.com");
    expect(utools.dbCryptoStorage.storage.get("dln.authToken")).toBe("secret-token");
  });

  it("builds authorized backend requests against the configured origin", async () => {
    const preload = loadPreloadModule();
    preload.__private.resetLaunchContext();
    const bridge = preload.createBridge();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: createHeaders("application/json", "req-chat-1"),
      json: async () => ({
        request_id: "req-chat-1",
        accepted: true,
      }),
    });
    globalThis.fetch = fetchMock as typeof fetch;

    await bridge.saveConfig({
      serverOrigin: "http://api.example.com/",
      authToken: "token-123",
    });

    await bridge.sendChatMessage({
      channel: "desktop_plugin",
      message_type: "text",
      text: "hello",
      client_message_id: "msg-1",
      occurred_at: "2026-03-14T12:00:00Z",
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.example.com/api/v1/chat/messages",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token-123",
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          channel: "desktop_plugin",
          message_type: "text",
          text: "hello",
          client_message_id: "msg-1",
          occurred_at: "2026-03-14T12:00:00Z",
        }),
      }),
    );
  });

  it("maps non-2xx responses into structured bridge errors", async () => {
    const preload = loadPreloadModule();
    preload.__private.resetLaunchContext();
    const bridge = preload.createBridge();
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: createHeaders("application/json", "req-dup-1"),
      json: async () => ({
        detail: "duplicate",
      }),
    }) as typeof fetch;

    await expect(
      bridge.sendChatMessage({
        channel: "desktop_plugin",
        message_type: "text",
        text: "hello",
        client_message_id: "msg-1",
        occurred_at: "2026-03-14T12:00:00Z",
      }),
    ).rejects.toMatchObject({
      message: "duplicate",
      status: 409,
      code: "duplicate_message",
      requestId: "req-dup-1",
    });
  });

  it("maps aborted requests to timeout errors", async () => {
    vi.useFakeTimers();
    const preload = loadPreloadModule();
    preload.__private.resetLaunchContext();
    const bridge = preload.createBridge();
    globalThis.fetch = vi.fn(
      (_url: string, init?: RequestInit) =>
        new Promise((_, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        }),
    ) as typeof fetch;

    const pingExpectation = expect(bridge.pingBackend()).rejects.toMatchObject({
      message: "Request timed out.",
      code: "timeout",
      status: 0,
    });
    await vi.advanceTimersByTimeAsync(preload.REQUEST_TIMEOUT_MS + 50);
    await pingExpectation;
    vi.useRealTimers();
  });
});
