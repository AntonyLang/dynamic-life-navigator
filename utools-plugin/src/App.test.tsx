import "./test/setup";

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import type {
  BridgeConfig,
  BridgeSuccess,
  ChatMessageResponse,
  DlnBridge,
  LaunchContext,
  RecommendationBriefResponse,
  RecommendationFeedbackResponse,
  RecommendationPullResponse,
  StateResponse,
  UserStateSnapshot,
} from "./types";

interface MockBridge extends DlnBridge {
  emitLaunchContext: (context: LaunchContext) => void;
  getState: ReturnType<typeof vi.fn>;
  sendChatMessage: ReturnType<typeof vi.fn>;
  pullRecommendation: ReturnType<typeof vi.fn>;
  getBrief: ReturnType<typeof vi.fn>;
  submitFeedback: ReturnType<typeof vi.fn>;
  getConfig: ReturnType<typeof vi.fn>;
  saveConfig: ReturnType<typeof vi.fn>;
  pingBackend: ReturnType<typeof vi.fn>;
}

function mockStateSnapshot(overrides?: Partial<UserStateSnapshot>): UserStateSnapshot {
  return {
    mental_energy: 72,
    physical_energy: 58,
    focus_mode: "focused",
    do_not_disturb_until: null,
    recent_context: "planning",
    last_updated_at: "2026-03-14T10:00:00Z",
    ...overrides,
  };
}

function createSuccess<T>(data: T, requestId = "req-1"): BridgeSuccess<T> {
  return {
    data,
    requestId,
  };
}

function createMockBridge(initialLaunchContext?: LaunchContext): MockBridge {
  let launchContext =
    initialLaunchContext ??
    ({
      code: "shell",
      type: "manual",
      payload: null,
      launchId: 0,
    } satisfies LaunchContext);
  const listeners = new Set<(context: LaunchContext) => void>();
  const config: BridgeConfig = {
    serverOrigin: "http://127.0.0.1:8000",
    authToken: null,
  };

  const bridge: MockBridge = {
    getLaunchContext: vi.fn(() => launchContext),
    subscribeLaunchContext: vi.fn((listener: (context: LaunchContext) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }),
    getState: vi.fn(async () =>
      createSuccess<StateResponse>({
        request_id: "req-state",
        state: mockStateSnapshot(),
      }),
    ),
    sendChatMessage: vi.fn(),
    pullRecommendation: vi.fn(),
    getBrief: vi.fn(),
    submitFeedback: vi.fn(),
    getConfig: vi.fn(async () => config),
    saveConfig: vi.fn(async (nextConfig: BridgeConfig) => nextConfig),
    pingBackend: vi.fn(),
    emitLaunchContext(context: LaunchContext) {
      launchContext = context;
      for (const listener of listeners) {
        listener(context);
      }
    },
  };

  return bridge;
}

describe("uTools App", () => {
  let bridge: MockBridge;

  beforeEach(() => {
    bridge = createMockBridge();
    window.dlnBridge = bridge;
  });

  afterEach(() => {
    delete window.dlnBridge;
  });

  it("sends chat, shows assistant ack, and transitions the message to synced", async () => {
    bridge.getState
      .mockResolvedValueOnce(
        createSuccess<StateResponse>({
          request_id: "req-state-1",
          state: mockStateSnapshot(),
        }),
      )
      .mockResolvedValueOnce(
        createSuccess<StateResponse>({
          request_id: "req-state-2",
          state: mockStateSnapshot({ focus_mode: "tired", mental_energy: 48 }),
        }),
      );
    bridge.sendChatMessage.mockResolvedValue(
      createSuccess<ChatMessageResponse>({
        request_id: "req-chat-1",
        event_id: "evt-1",
        state: mockStateSnapshot({ focus_mode: "tired", mental_energy: 48 }),
        assistant_reply: "Recorded. I am updating your state now.",
        suggest_next_action: false,
        accepted: true,
        processing: true,
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("focused");
    await user.type(screen.getByPlaceholderText(/刚做完很重的脑力活/i), "Need one clear next step.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Recorded. I am updating your state now.");
    expect(bridge.sendChatMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "Need one clear next step.",
        channel: "desktop_plugin",
      }),
    );
    await screen.findByText("synced");
    expect(screen.getByText("tired")).toBeInTheDocument();
  });

  it("routes /pull through the command dispatcher without calling chat ingest", async () => {
    bridge.getState.mockResolvedValue(
      createSuccess<StateResponse>({
        request_id: "req-state-1",
        state: mockStateSnapshot(),
      }),
    );
    bridge.pullRecommendation.mockResolvedValue(
      createSuccess<RecommendationPullResponse>({
        request_id: "req-pull-1",
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
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("focused");
    await user.type(screen.getByPlaceholderText(/刚做完很重的脑力活/i), "/pull");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findAllByText("Protect focus block");
    expect(bridge.pullRecommendation).toHaveBeenCalledWith({ limit: 2 });
    expect(bridge.sendChatMessage).not.toHaveBeenCalled();
  });

  it("routes /brief through the command dispatcher and opens the brief drawer", async () => {
    bridge.getState.mockResolvedValue(
      createSuccess<StateResponse>({
        request_id: "req-state-1",
        state: mockStateSnapshot(),
      }),
    );
    bridge.getBrief.mockResolvedValue(
      createSuccess<RecommendationBriefResponse>({
        request_id: "req-brief-1",
        summary: {
          active_projects: 3,
          active_values: 2,
          urgent_nodes: 1,
          stale_nodes: 1,
        },
        items: [
          {
            node_id: "node-1",
            title: "Project checkpoint",
            status: "active",
            health: "steady",
            next_hint: "Review the remaining integration edge cases.",
          },
        ],
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("focused");
    await user.type(screen.getByPlaceholderText(/刚做完很重的脑力活/i), "/brief");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByRole("dialog");
    expect(screen.getByText("Project checkpoint")).toBeInTheDocument();
    expect(bridge.getBrief).toHaveBeenCalledTimes(1);
    expect(bridge.sendChatMessage).not.toHaveBeenCalled();
  });

  it("repulls a new recommendation after dismissed feedback", async () => {
    bridge.getState.mockResolvedValue(
      createSuccess<StateResponse>({
        request_id: "req-state-1",
        state: mockStateSnapshot(),
      }),
    );
    bridge.pullRecommendation
      .mockResolvedValueOnce(
        createSuccess<RecommendationPullResponse>({
          request_id: "req-pull-1",
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
        }),
      )
      .mockResolvedValueOnce(
        createSuccess<RecommendationPullResponse>({
          request_id: "req-pull-2",
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
        }),
      );
    bridge.submitFeedback.mockResolvedValue(
      createSuccess<RecommendationFeedbackResponse>({
        request_id: "req-feedback-1",
        recommendation_id: "rec-1",
        accepted: true,
        feedback: "dismissed",
      }),
    );

    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("focused");
    await user.click(screen.getByRole("button", { name: "Pull recommendation" }));
    await screen.findAllByText("Finish the bugfix");
    await user.click(screen.getByRole("button", { name: "Swap" }));

    await screen.findAllByText("Review the roadmap");
    expect(bridge.submitFeedback).toHaveBeenCalledWith("rec-1", {
      feedback: "dismissed",
      node_id: "node-1",
      channel: "desktop_plugin",
    });
    expect(bridge.pullRecommendation).toHaveBeenNthCalledWith(2, { limit: 1 });
  });

  it("processes shell, pull, brief, and image launch contexts", async () => {
    bridge = createMockBridge({
      code: "shell",
      type: "text",
      payload: "prefilled launch text",
      launchId: 1,
    });
    bridge.getState.mockResolvedValue(
      createSuccess<StateResponse>({
        request_id: "req-state-1",
        state: mockStateSnapshot(),
      }),
    );
    bridge.pullRecommendation.mockResolvedValue(
      createSuccess<RecommendationPullResponse>({
        request_id: "req-pull-1",
        recommendation_id: "rec-1",
        mode: "pull",
        empty_state: false,
        fallback_message: null,
        items: [
          {
            node_id: "node-1",
            title: "Take a quick recovery walk",
            message: "Use a low-load reset before the next block.",
            reason_tags: ["state_match"],
          },
        ],
      }),
    );
    bridge.getBrief.mockResolvedValue(
      createSuccess<RecommendationBriefResponse>({
        request_id: "req-brief-1",
        summary: {
          active_projects: 1,
          active_values: 1,
          urgent_nodes: 0,
          stale_nodes: 0,
        },
        items: [
          {
            node_id: "node-brief",
            title: "Brief item",
            status: "active",
            health: "steady",
            next_hint: "Keep the cadence stable.",
          },
        ],
      }),
    );
    window.dlnBridge = bridge;

    render(<App />);

    const textarea = await screen.findByPlaceholderText(/刚做完很重的脑力活/i);
    expect(textarea).toHaveValue("prefilled launch text");

    await act(async () => {
      bridge.emitLaunchContext({
        code: "pull",
        type: "manual",
        payload: null,
        launchId: 2,
      });
    });
    await screen.findAllByText("Take a quick recovery walk");

    await act(async () => {
      bridge.emitLaunchContext({
        code: "brief",
        type: "manual",
        payload: null,
        launchId: 3,
      });
    });
    await screen.findByText("Brief item");

    await act(async () => {
      bridge.emitLaunchContext({
        code: "shell",
        type: "img",
        payload: {
          imgPath: "C:/tmp/test.png",
        },
        launchId: 4,
      });
    });
    await screen.findByText("已收到图片，暂未解析。");
  });
});
