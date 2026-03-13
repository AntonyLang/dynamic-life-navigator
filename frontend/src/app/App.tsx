import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import styles from "./App.module.css";
import { useDebugEvents } from "./hooks/useDebugEvents";
import { useChatFlow } from "./hooks/useChatFlow";
import { useDevActions } from "./hooks/useDevActions";
import { useRecommendationFlow } from "./hooks/useRecommendationFlow";
import { makeId, toErrorMessage } from "./hooks/flowUtils";
import { useAppStore } from "./store";
import { BriefPanel } from "../features/brief/BriefPanel";
import { ChatInput } from "../features/chat/ChatInput";
import { ChatTimeline } from "../features/chat/ChatTimeline";
import { DevPanel } from "../features/devtools/DevPanel";
import { RecommendationSidebar } from "../features/recommendations/RecommendationSidebar";
import { StateBar } from "../features/state/StateBar";
import { apiClient } from "../lib/api/client";

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
    debugEvents,
    setInputValue,
    appendEntry,
    setLatestBrief,
    setBriefOpen,
    setDevOpen,
  } = useAppStore();

  const { writeDebugEvent } = useDebugEvents();

  function appendSystemNotice(text: string, tone: "info" | "error" = "info") {
    appendEntry({
      id: makeId("system"),
      kind: "system",
      text,
      tone,
    });
  }

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

  const { sendChatMessage, retryChatMessage, isChatPending } = useChatFlow({
    appendSystemNotice,
    writeDebugEvent,
  });

  const { handlePull, handleRecommendationFeedback, isPullPending } = useRecommendationFlow({
    appendSystemNotice,
    writeDebugEvent,
    isBriefOpen,
  });

  const { handleResetState, handleCreateNode, isDevActionPending } = useDevActions({
    appendSystemNotice,
    writeDebugEvent,
    isBriefOpen,
    refreshRecommendationsSilently: () => handlePull(2, { addToTimeline: false }),
  });

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

  async function handleInputSubmit(rawText: string) {
    const text = rawText.trim();
    if (!text) {
      return;
    }

    setInputValue("");

    if (text === "/pull") {
      await handlePull(2, { addToTimeline: true });
      return;
    }

    if (text === "/brief") {
      await handleBrief();
      return;
    }

    await sendChatMessage(text);
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
            lastSuccessfulAt={stateQuery.dataUpdatedAt || null}
          />

          <section className={styles.timelineCard}>
            <ChatTimeline
              entries={timeline}
              onRetryMessage={retryChatMessage}
              onRecommendationFeedback={handleRecommendationFeedback}
            />
          </section>

          <section className={styles.inputCard}>
            <ChatInput
              value={inputValue}
              onChange={setInputValue}
              onSend={handleInputSubmit}
              onPull={() => void handlePull(2, { addToTimeline: true })}
              onBrief={() => void handleBrief()}
              onQuickFill={setInputValue}
              disabled={isChatPending || isPullPending}
            />
          </section>
        </div>

        <aside className={styles.sideColumn}>
          <RecommendationSidebar
            recommendation={latestRecommendation}
            loading={isPullPending}
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
            debugEvents={debugEvents}
            busy={isDevActionPending}
          />
        </aside>
      </div>
    </div>
  );
}
