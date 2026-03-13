import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import styles from "./App.module.css";
import { useAppStore } from "./store";
import { BriefPanel } from "../features/brief/BriefPanel";
import { ChatInput } from "../features/chat/ChatInput";
import { ChatTimeline } from "../features/chat/ChatTimeline";
import { DevPanel } from "../features/devtools/DevPanel";
import { RecommendationSidebar } from "../features/recommendations/RecommendationSidebar";
import { StateBar } from "../features/state/StateBar";
import { apiClient } from "../lib/api/client";
import type { ApiSuccess, ChatMessageRequest, RecommendationFeedbackRequest, StateResponse } from "../lib/api/types";
import { ApiError } from "../lib/api/types";

function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function reconcileState(
  fetchState: () => Promise<ApiSuccess<StateResponse>>,
  onSuccess: (result: ApiSuccess<StateResponse>) => void,
  onExhausted: () => void,
) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await sleep(2000);
    try {
      const result = await fetchState();
      onSuccess(result);
      return;
    } catch {
      // Keep polling briefly after the synchronous ack path succeeds.
    }
  }

  onExhausted();
}

function toErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed. Please try again.";
}

export function App() {
  const queryClient = useQueryClient();
  const {
    inputValue,
    timeline,
    latestRecommendation,
    latestBrief,
    isBriefOpen,
    isDevOpen,
    lastDebugEvent,
    setInputValue,
    appendEntry,
    updateEntry,
    setLatestRecommendation,
    setLatestBrief,
    setBriefOpen,
    setDevOpen,
    logDebugEvent,
  } = useAppStore();

  const stateQuery = useQuery({
    queryKey: ["state"],
    queryFn: () => apiClient.getState(),
    refetchInterval: () => (document.visibilityState === "visible" ? 20_000 : false),
    refetchIntervalInBackground: false,
  });

  const briefQuery = useQuery({
    queryKey: ["brief"],
    queryFn: () => apiClient.getBrief(),
    enabled: isBriefOpen,
  });

  useEffect(() => {
    if (briefQuery.data) {
      setLatestBrief(briefQuery.data.data);
    }
  }, [briefQuery.data, setLatestBrief]);

  const chatMutation = useMutation({
    mutationFn: (payload: ChatMessageRequest) => apiClient.sendChatMessage(payload),
  });

  const pullMutation = useMutation({
    mutationFn: (limit: number) => apiClient.pullRecommendation(limit),
  });

  const feedbackMutation = useMutation({
    mutationFn: (payload: { recommendationId: string; body: RecommendationFeedbackRequest }) =>
      apiClient.submitFeedback(payload.recommendationId, payload.body),
  });

  const resetMutation = useMutation({
    mutationFn: apiClient.resetState,
  });

  const createNodeMutation = useMutation({
    mutationFn: apiClient.createNode,
  });

  function writeDebugEvent(
    label: string,
    response: unknown,
    extras?: { requestId?: string | null; eventId?: string | null; recommendationId?: string | null },
  ) {
    logDebugEvent({
      label,
      requestId: extras?.requestId ?? null,
      eventId: extras?.eventId ?? null,
      recommendationId: extras?.recommendationId ?? null,
      response,
      createdAt: new Date().toISOString(),
    });
  }

  function appendSystemNotice(text: string, tone: "info" | "error" = "info") {
    appendEntry({
      id: makeId("system"),
      kind: "system",
      text,
      tone,
    });
  }

  function updateRecommendationEntries(
    recommendationId: string,
    status: "feedback_submitting" | "feedback_done" | "feedback_failed",
  ) {
    for (const entry of useAppStore.getState().timeline) {
      if (entry.kind === "recommendation" && entry.recommendationId === recommendationId) {
        updateEntry(entry.id, (current) =>
          current.kind === "recommendation"
            ? {
                ...current,
                status,
              }
            : current,
        );
      }
    }
  }

  async function handlePull(limit = 2, options?: { addToTimeline?: boolean }) {
    const addToTimeline = options?.addToTimeline ?? true;
    const timelineEntryId = addToTimeline ? makeId("rec") : null;

    if (timelineEntryId) {
      appendEntry({
        id: timelineEntryId,
        kind: "recommendation",
        recommendationId: "loading",
        emptyState: false,
        items: [],
        fallbackMessage: null,
        status: "loading",
      });
    }

    try {
      const result = await pullMutation.mutateAsync(limit);
      setLatestRecommendation(result.data);
      writeDebugEvent("recommendations.next", result.data, {
        requestId: result.requestId,
        recommendationId: result.data.recommendation_id,
      });

      if (timelineEntryId) {
        updateEntry(timelineEntryId, (entry) =>
          entry.kind === "recommendation"
            ? {
                ...entry,
                recommendationId: result.data.recommendation_id,
                emptyState: result.data.empty_state,
                items: result.data.items,
                fallbackMessage: result.data.fallback_message,
                status: result.data.empty_state ? "empty" : "ready",
              }
            : entry,
        );
      }

      return result.data;
    } catch (error) {
      if (timelineEntryId) {
        updateEntry(timelineEntryId, (entry) =>
          entry.kind === "recommendation"
            ? {
                ...entry,
                emptyState: true,
                status: "feedback_failed",
                fallbackMessage: toErrorMessage(error),
              }
            : entry,
        );
      }
      appendSystemNotice(toErrorMessage(error), "error");
      return null;
    }
  }

  async function handleBrief() {
    setBriefOpen(true);
    try {
      const result = await queryClient.fetchQuery({
        queryKey: ["brief"],
        queryFn: () => apiClient.getBrief(),
      });

      setLatestBrief(result.data);
      writeDebugEvent("brief.fetch", result.data, {
        requestId: result.requestId,
      });
    } catch (error) {
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  async function submitChatText(text: string, entryId: string) {
    try {
      const result = await chatMutation.mutateAsync({
        channel: "frontend_web_shell",
        message_type: "text",
        text,
        client_message_id: makeId("client-message"),
        occurred_at: new Date().toISOString(),
      });

      updateEntry(entryId, (entry) =>
        entry.kind === "user"
          ? {
              ...entry,
              status: "processing",
            }
          : entry,
      );

      queryClient.setQueryData<ApiSuccess<StateResponse>>(["state"], {
        requestId: result.requestId,
        data: {
          request_id: result.data.request_id,
          state: result.data.state,
        },
      });

      appendEntry({
        id: makeId("assistant"),
        kind: "assistant",
        text: result.data.assistant_reply,
        requestId: result.requestId,
        eventId: result.data.event_id,
      });

      writeDebugEvent("chat.message", result.data, {
        requestId: result.requestId,
        eventId: result.data.event_id,
      });

      void reconcileState(
        () => apiClient.getState(),
        (stateResult) => {
          queryClient.setQueryData(["state"], stateResult);
          void queryClient.invalidateQueries({ queryKey: ["state"] });
          updateEntry(entryId, (entry) =>
            entry.kind === "user"
              ? {
                  ...entry,
                  status: "synced",
                }
              : entry,
          );
        },
        () => {
          updateEntry(entryId, (entry) =>
            entry.kind === "user"
              ? {
                  ...entry,
                  status: "synced",
                }
              : entry,
          );
          appendSystemNotice("Message accepted. State sync will refresh shortly.");
        },
      );
    } catch (error) {
      updateEntry(entryId, (entry) =>
        entry.kind === "user"
          ? {
              ...entry,
              status: "failed",
              errorMessage: toErrorMessage(error),
            }
          : entry,
      );
    }
  }

  async function handleSend(rawText: string) {
    const text = rawText.trim();
    if (!text) {
      return;
    }

    if (text === "/pull") {
      setInputValue("");
      await handlePull(2, { addToTimeline: true });
      return;
    }

    if (text === "/brief") {
      setInputValue("");
      await handleBrief();
      return;
    }

    const entryId = makeId("user");
    setInputValue("");
    appendEntry({
      id: entryId,
      kind: "user",
      text,
      status: "sending",
    });

    await submitChatText(text, entryId);
  }

  async function handleRecommendationFeedback(
    recommendationId: string,
    nodeId: string | null,
    feedback: RecommendationFeedbackRequest["feedback"],
  ) {
    updateRecommendationEntries(recommendationId, "feedback_submitting");

    try {
      const result = await feedbackMutation.mutateAsync({
        recommendationId,
        body: {
          feedback,
          node_id: nodeId,
          channel: "frontend_web_shell",
        },
      });

      writeDebugEvent("recommendations.feedback", result.data, {
        requestId: result.requestId,
        recommendationId,
      });
      updateRecommendationEntries(recommendationId, "feedback_done");

      if (feedback === "dismissed") {
        await handlePull(1, { addToTimeline: true });
      } else {
        appendSystemNotice(`Feedback recorded: ${feedback}.`);
      }

      if (isBriefOpen) {
        void queryClient.invalidateQueries({ queryKey: ["brief"] });
      }
      void queryClient.invalidateQueries({ queryKey: ["state"] });
    } catch (error) {
      updateRecommendationEntries(recommendationId, "feedback_failed");
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  async function handleResetState(payload: { mental_energy: number; physical_energy: number; reason: string }) {
    try {
      const result = await resetMutation.mutateAsync(payload);
      queryClient.setQueryData<ApiSuccess<StateResponse>>(["state"], {
        requestId: result.requestId,
        data: {
          request_id: result.data.request_id,
          state: result.data.state,
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["state"] });
      if (isBriefOpen) {
        void queryClient.invalidateQueries({ queryKey: ["brief"] });
      }
      void handlePull(2, { addToTimeline: false });
      writeDebugEvent("state.reset", result.data, {
        requestId: result.requestId,
      });
      appendSystemNotice("State reset completed.");
    } catch (error) {
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  async function handleCreateNode(payload: Parameters<typeof apiClient.createNode>[0]) {
    try {
      const result = await createNodeMutation.mutateAsync(payload);
      if (isBriefOpen) {
        void queryClient.invalidateQueries({ queryKey: ["brief"] });
      }
      void handlePull(2, { addToTimeline: false });
      writeDebugEvent("nodes.create", result.data, {
        requestId: result.requestId,
      });
      appendSystemNotice(`Node created: ${result.data.node.title}.`);
    } catch (error) {
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  async function handleRetryMessage(entryId: string) {
    const entry = useAppStore.getState().timeline.find((item) => item.id === entryId);
    if (entry?.kind !== "user") {
      return;
    }

    updateEntry(entryId, (current) =>
      current.kind === "user"
        ? {
            ...current,
            status: "sending",
            errorMessage: undefined,
          }
        : current,
    );
    await submitChatText(entry.text, entryId);
  }

  const state = stateQuery.data?.data.state ?? null;
  const stateError = stateQuery.error ? toErrorMessage(stateQuery.error) : null;

  return (
    <div className={styles.shell}>
      <div className={styles.layout}>
        <div className={styles.mainColumn}>
          <section className={styles.headerCard}>
            <p className={styles.eyebrow}>Dynamic Life Navigator</p>
            <div className={styles.titleRow}>
              <div>
                <h1 className={styles.title}>Frontend MVP Shell</h1>
                <p className={styles.subtitle}>
                  This thin client keeps the integration path short: message input, state reflection, recommendation
                  feedback, brief viewing, and a few developer helpers.
                </p>
              </div>
              <div className={styles.headerActions}>
                <button className={styles.secondaryButton} type="button" onClick={() => setBriefOpen(!isBriefOpen)}>
                  {isBriefOpen ? "Hide brief" : "Open brief"}
                </button>
                <button className={styles.primaryButton} type="button" onClick={() => setDevOpen(!isDevOpen)}>
                  {isDevOpen ? "Hide dev panel" : "Open dev panel"}
                </button>
              </div>
            </div>
          </section>

          <StateBar
            state={state}
            stale={Boolean(stateQuery.error)}
            loading={stateQuery.isLoading}
            errorMessage={stateError}
          />

          <section className={styles.timelineCard}>
            <ChatTimeline
              entries={timeline}
              onRetryMessage={handleRetryMessage}
              onRecommendationFeedback={handleRecommendationFeedback}
            />
          </section>

          <section className={styles.inputCard}>
            <ChatInput
              value={inputValue}
              onChange={setInputValue}
              onSend={handleSend}
              onPull={() => void handlePull(2, { addToTimeline: true })}
              onBrief={() => void handleBrief()}
              onQuickFill={setInputValue}
              disabled={chatMutation.isPending || pullMutation.isPending}
            />
          </section>
        </div>

        <aside className={styles.sideColumn}>
          <RecommendationSidebar
            recommendation={latestRecommendation}
            loading={pullMutation.isPending}
            onPull={() => void handlePull(2, { addToTimeline: true })}
            onPrefill={setInputValue}
          />
          <BriefPanel
            brief={latestBrief}
            loading={briefQuery.isFetching}
            open={isBriefOpen}
            onToggle={() => setBriefOpen(!isBriefOpen)}
            onRefresh={() => void handleBrief()}
          />
          <DevPanel
            open={isDevOpen}
            onToggle={() => setDevOpen(!isDevOpen)}
            onResetState={handleResetState}
            onCreateNode={handleCreateNode}
            lastDebugEvent={lastDebugEvent}
            busy={resetMutation.isPending || createNodeMutation.isPending}
          />
        </aside>
      </div>
    </div>
  );
}
