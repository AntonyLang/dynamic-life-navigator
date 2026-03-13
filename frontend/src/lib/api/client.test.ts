import "../../test/setup";

import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";

describe("apiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("parses a successful state response and keeps X-Request-Id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            request_id: "req-1",
            state: {
              mental_energy: 70,
              physical_energy: 55,
              focus_mode: "deep_work",
              do_not_disturb_until: null,
              recent_context: "debugging",
              last_updated_at: "2026-03-13T09:00:00Z",
            },
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
              "X-Request-Id": "req-1",
            },
          },
        ),
      ),
    );

    const result = await apiClient.getState();

    expect(result.requestId).toBe("req-1");
    expect(result.data.state.focus_mode).toBe("deep_work");
  });

  it("maps 409 chat duplicates to a dedicated ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "duplicate" }), {
          status: 409,
          headers: {
            "Content-Type": "application/json",
            "X-Request-Id": "req-dup",
          },
        }),
      ),
    );

    await expect(
      apiClient.sendChatMessage({
        channel: "frontend_web_shell",
        message_type: "text",
        text: "hello",
        client_message_id: "dup-1",
        occurred_at: "2026-03-13T09:00:00Z",
      }),
    ).rejects.toMatchObject({
      status: 409,
      code: "duplicate_message",
      requestId: "req-dup",
      message: "Message was already submitted.",
    });
  });

  it("maps fetch aborts to timeout errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));

    await expect(apiClient.getState()).rejects.toMatchObject({
      code: "timeout",
      message: "Request timed out.",
    });
  });
});
