import "../test/setup";

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api/client", () => ({
  apiClient: {
    getState: vi.fn(),
    sendChatMessage: vi.fn(),
    pullRecommendation: vi.fn(),
    getBrief: vi.fn(),
    submitFeedback: vi.fn(),
    resetState: vi.fn(),
    createNode: vi.fn(),
  },
}));

import { App } from "./App";
import { useAppStore } from "./store";
import { apiClient } from "../lib/api/client";
import type { UserStateSnapshot } from "../lib/api/types";
import { renderWithProviders } from "../test/render";

const mockedApiClient = vi.mocked(apiClient);

function mockStateSnapshot(overrides?: Partial<UserStateSnapshot>) {
  return {
    mental_energy: 72,
    physical_energy: 58,
    focus_mode: "deep_work",
    do_not_disturb_until: null,
    recent_context: "planning",
    last_updated_at: "2026-03-13T10:00:00Z",
    ...overrides,
  };
}

describe("App integration", () => {
  beforeEach(() => {
    useAppStore.getState().resetForTests();
    mockedApiClient.getState.mockReset();
    mockedApiClient.sendChatMessage.mockReset();
    mockedApiClient.pullRecommendation.mockReset();
    mockedApiClient.getBrief.mockReset();
    mockedApiClient.submitFeedback.mockReset();
    mockedApiClient.resetState.mockReset();
    mockedApiClient.createNode.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("sends chat, shows assistant ack, and refreshes state cache", async () => {
    mockedApiClient.getState
      .mockResolvedValueOnce({
        requestId: "req-state-1",
        data: {
          request_id: "req-state-1",
          state: mockStateSnapshot(),
        },
      })
      .mockResolvedValueOnce({
        requestId: "req-state-2",
        data: {
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "recovery", mental_energy: 48 }),
        },
      })
      .mockResolvedValue({
        requestId: "req-state-2",
        data: {
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "recovery", mental_energy: 48 }),
        },
      });

    mockedApiClient.sendChatMessage.mockResolvedValue({
      requestId: "req-chat-1",
      data: {
        request_id: "req-chat-1",
        event_id: "evt-1",
        state: mockStateSnapshot({ focus_mode: "recovery", mental_energy: 48 }),
        assistant_reply: "Take a short reset before choosing the next task.",
        suggest_next_action: true,
        accepted: true,
        processing: true,
      },
    });

    const user = userEvent.setup();
    renderWithProviders(<App />);

    await screen.findByText("deep_work");
    await user.type(screen.getByPlaceholderText(/I just finished a heavy debugging session/i), "Need one clear next step.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Take a short reset before choosing the next task.");
    expect(mockedApiClient.sendChatMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "Need one clear next step.",
        channel: "frontend_web_shell",
      }),
    );
    expect(screen.getByText("recovery")).toBeInTheDocument();
    await screen.findByText("synced", {}, { timeout: 3_000 });
  });

  it("routes /pull only through the app-level command dispatcher", async () => {
    mockedApiClient.getState.mockResolvedValue({
      requestId: "req-state-1",
      data: {
        request_id: "req-state-1",
        state: mockStateSnapshot(),
      },
    });
    mockedApiClient.pullRecommendation.mockResolvedValue({
      requestId: "req-rec-1",
      data: {
        request_id: "req-rec-1",
        recommendation_id: "rec-1",
        mode: "pull",
        empty_state: false,
        fallback_message: null,
        items: [
          {
            node_id: "node-1",
            title: "Protect focus block",
            message: "Keep one uninterrupted hour.",
            reason_tags: ["state_match"],
          },
        ],
      },
    });

    const user = userEvent.setup();
    renderWithProviders(<App />);

    await screen.findByText("deep_work");
    await user.type(screen.getByPlaceholderText(/I just finished a heavy debugging session/i), "/pull");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getAllByText("Protect focus block")).toHaveLength(2);
    });
    expect(mockedApiClient.pullRecommendation).toHaveBeenCalledWith(2);
    expect(mockedApiClient.sendChatMessage).not.toHaveBeenCalled();
  });

  it("repulls a new recommendation after dismissed feedback", async () => {
    mockedApiClient.getState.mockResolvedValue({
      requestId: "req-state-1",
      data: {
        request_id: "req-state-1",
        state: mockStateSnapshot(),
      },
    });
    mockedApiClient.pullRecommendation
      .mockResolvedValueOnce({
        requestId: "req-rec-1",
        data: {
          request_id: "req-rec-1",
          recommendation_id: "rec-1",
          mode: "pull",
          empty_state: false,
          fallback_message: null,
          items: [
            {
              node_id: "node-1",
              title: "Finish the bugfix",
              message: "Close the highest leverage thread.",
              reason_tags: ["urgent"],
            },
          ],
        },
      })
      .mockResolvedValueOnce({
        requestId: "req-rec-2",
        data: {
          request_id: "req-rec-2",
          recommendation_id: "rec-2",
          mode: "pull",
          empty_state: false,
          fallback_message: null,
          items: [
            {
              node_id: "node-2",
              title: "Review the roadmap",
              message: "Use the calmer option instead.",
              reason_tags: ["alternate"],
            },
          ],
        },
      });
    mockedApiClient.submitFeedback.mockResolvedValue({
      requestId: "req-feedback-1",
      data: {
        request_id: "req-feedback-1",
        recommendation_id: "rec-1",
        accepted: true,
        feedback: "dismissed",
      },
    });

    const user = userEvent.setup();
    renderWithProviders(<App />);

    await screen.findByText("deep_work");
    await user.click(screen.getAllByRole("button", { name: "Pull" })[0]);
    await waitFor(() => {
      expect(screen.getAllByText("Finish the bugfix")).toHaveLength(2);
    });
    await user.click(screen.getByRole("button", { name: "Swap" }));

    await waitFor(() => {
      expect(screen.getAllByText("Review the roadmap")).toHaveLength(2);
    });
    expect(mockedApiClient.submitFeedback).toHaveBeenCalledWith("rec-1", {
      feedback: "dismissed",
      node_id: "node-1",
      channel: "frontend_web_shell",
    });
    expect(mockedApiClient.pullRecommendation).toHaveBeenNthCalledWith(2, 1);
  });

  it("retries a failed chat message without duplicating the user bubble", async () => {
    mockedApiClient.getState
      .mockResolvedValueOnce({
        requestId: "req-state-1",
        data: {
          request_id: "req-state-1",
          state: mockStateSnapshot(),
        },
      })
      .mockResolvedValueOnce({
        requestId: "req-state-2",
        data: {
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "recovery" }),
        },
      })
      .mockResolvedValue({
        requestId: "req-state-2",
        data: {
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "recovery" }),
        },
      });
    mockedApiClient.sendChatMessage
      .mockRejectedValueOnce(new Error("Network request failed."))
      .mockResolvedValueOnce({
        requestId: "req-chat-2",
        data: {
          request_id: "req-chat-2",
          event_id: "evt-2",
          state: mockStateSnapshot({ focus_mode: "recovery" }),
          assistant_reply: "Try the calmer path.",
          suggest_next_action: true,
          accepted: true,
          processing: true,
        },
      });

    const user = userEvent.setup();
    renderWithProviders(<App />);

    await screen.findByText("deep_work");
    await user.type(screen.getByPlaceholderText(/I just finished a heavy debugging session/i), "Need one clear next step.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByRole("button", { name: "Retry" });
    expect(screen.getAllByText("Need one clear next step.")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Retry" }));
    await screen.findByText("Try the calmer path.");
    await screen.findByText("synced", {}, { timeout: 3_000 });
    expect(mockedApiClient.sendChatMessage).toHaveBeenCalledTimes(2);
    expect(screen.getAllByText("Need one clear next step.")).toHaveLength(1);
  });

  it("runs reset state through dev actions and silently refreshes recommendations", async () => {
    mockedApiClient.getState
      .mockResolvedValueOnce({
        requestId: "req-state-1",
        data: {
          request_id: "req-state-1",
          state: mockStateSnapshot(),
        },
      })
      .mockResolvedValueOnce({
        requestId: "req-state-2",
        data: {
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "reset_mode", mental_energy: 61 }),
        },
      })
      .mockResolvedValue({
        requestId: "req-state-2",
        data: {
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "reset_mode", mental_energy: 61 }),
        },
      });
    mockedApiClient.resetState.mockResolvedValue({
      requestId: "req-reset-1",
      data: {
        request_id: "req-reset-1",
        state: mockStateSnapshot({ focus_mode: "reset_mode", mental_energy: 61 }),
        reset_reason: "frontend manual reset",
        updated_at: "2026-03-13T10:02:00Z",
      },
    });
    mockedApiClient.pullRecommendation.mockResolvedValue({
      requestId: "req-rec-1",
      data: {
        request_id: "req-rec-1",
        recommendation_id: "rec-1",
        mode: "pull",
        empty_state: true,
        fallback_message: "No strong candidate right now.",
        items: [],
      },
    });

    const user = userEvent.setup();
    renderWithProviders(<App />);

    await screen.findByText("deep_work");
    await user.click(screen.getByRole("button", { name: "Submit reset" }));

    await waitFor(() => {
      expect(mockedApiClient.resetState).toHaveBeenCalled();
    });
    expect(mockedApiClient.pullRecommendation).toHaveBeenCalledWith(2);
    expect(screen.getByText("reset_mode")).toBeInTheDocument();
    expect(screen.getByText("State reset completed.")).toBeInTheDocument();
  });
});
