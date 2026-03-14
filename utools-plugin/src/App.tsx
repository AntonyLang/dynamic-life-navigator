import { useEffect, useMemo, useRef, useState } from "react";

import { bridgeClient } from "./bridge";
import { BriefDrawer } from "./components/BriefDrawer";
import { InputPanel } from "./components/InputPanel";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { StatePanel } from "./components/StatePanel";
import { Timeline } from "./components/Timeline";
import type {
  BridgeConfig,
  LaunchContext,
  PingBackendResult,
  RecommendationBriefResponse,
  RecommendationFeedbackType,
  RecommendationPullResponse,
  TimelineEntry,
  UserStateSnapshot,
} from "./types";
import { makeId, reconcileState, toErrorMessage } from "./utils";

function appendEntry(setter: React.Dispatch<React.SetStateAction<TimelineEntry[]>>, entry: TimelineEntry) {
  setter((current) => [...current, entry]);
}

function updateEntry(
  setter: React.Dispatch<React.SetStateAction<TimelineEntry[]>>,
  id: string,
  updater: (entry: TimelineEntry) => TimelineEntry,
) {
  setter((current) => current.map((entry) => (entry.id === id ? updater(entry) : entry)));
}

function updateRecommendationEntries(
  setter: React.Dispatch<React.SetStateAction<TimelineEntry[]>>,
  recommendationId: string,
  status: Extract<TimelineEntry, { kind: "recommendation" }>["status"],
  errorMessage?: string,
) {
  setter((current) =>
    current.map((entry) =>
      entry.kind === "recommendation" && entry.recommendationId === recommendationId
        ? {
            ...entry,
            status,
            errorMessage,
          }
        : entry,
    ),
  );
}

function extractLaunchText(context: LaunchContext) {
  if (context.type === "text" && typeof context.payload === "string") {
    return context.payload.trim();
  }

  if (context.payload && typeof context.payload === "object" && "text" in context.payload) {
    const payloadText = context.payload.text;
    if (typeof payloadText === "string") {
      return payloadText.trim();
    }
  }

  return "";
}

function hasImagePayload(context: LaunchContext) {
  if (context.type === "img") {
    return true;
  }

  if (context.payload && typeof context.payload === "object") {
    if ("imgPath" in context.payload || "path" in context.payload) {
      return true;
    }
  }

  return false;
}

export function App() {
  const [stateSnapshot, setStateSnapshot] = useState<UserStateSnapshot | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [latestRecommendation, setLatestRecommendation] = useState<RecommendationPullResponse | null>(null);
  const [brief, setBrief] = useState<RecommendationBriefResponse | null>(null);
  const [configDraft, setConfigDraft] = useState<BridgeConfig>({
    serverOrigin: "http://127.0.0.1:8000",
    authToken: null,
  });
  const [isBriefOpen, setBriefOpen] = useState(false);
  const [isSettingsOpen, setSettingsOpen] = useState(false);
  const [loadingState, setLoadingState] = useState(true);
  const [stateErrorMessage, setStateErrorMessage] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const [lastSuccessfulAt, setLastSuccessfulAt] = useState<number | null>(null);
  const [chatPending, setChatPending] = useState(false);
  const [pullPending, setPullPending] = useState(false);
  const [briefLoading, setBriefLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [pingResult, setPingResult] = useState<PingBackendResult | null>(null);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [launchContext, setLaunchContext] = useState<LaunchContext>(bridgeClient.getLaunchContext());
  const processedLaunchIdRef = useRef<number>(-1);

  const busy = useMemo(() => chatPending || pullPending, [chatPending, pullPending]);

  function appendSystemNotice(text: string, tone: "info" | "error" = "info") {
    appendEntry(setTimeline, {
      id: makeId("system"),
      kind: "system",
      text,
      tone,
    });
  }

  async function refreshState(options?: { silent?: boolean }) {
    const silent = options?.silent ?? false;
    if (!silent) {
      setLoadingState(true);
    }

    try {
      const result = await bridgeClient.getState();
      setStateSnapshot(result.data.state);
      setConnectionStatus("connected");
      setStateErrorMessage(null);
      setLastSuccessfulAt(Date.now());
      return result;
    } catch (error) {
      setConnectionStatus("disconnected");
      setStateErrorMessage(toErrorMessage(error));
      if (!silent && !stateSnapshot) {
        appendSystemNotice(toErrorMessage(error), "error");
      }
      return null;
    } finally {
      if (!silent) {
        setLoadingState(false);
      }
    }
  }

  async function loadBrief(options?: { silent?: boolean }) {
    const silent = options?.silent ?? false;
    setBriefLoading(true);
    try {
      const result = await bridgeClient.getBrief();
      setBrief(result.data);
      setBriefOpen(true);
      return result.data;
    } catch (error) {
      if (!silent) {
        appendSystemNotice(toErrorMessage(error), "error");
      }
      return null;
    } finally {
      setBriefLoading(false);
    }
  }

  async function handlePull(limit = 2, options?: { addToTimeline?: boolean }) {
    const addToTimeline = options?.addToTimeline ?? true;
    const timelineEntryId = addToTimeline ? makeId("recommendation") : null;

    if (timelineEntryId) {
      appendEntry(setTimeline, {
        id: timelineEntryId,
        kind: "recommendation",
        recommendationId: "loading",
        emptyState: false,
        items: [],
        fallbackMessage: null,
        status: "loading",
      });
    }

    setPullPending(true);
    try {
      const result = await bridgeClient.pullRecommendation(limit);
      setLatestRecommendation(result.data);

      if (timelineEntryId) {
        updateEntry(setTimeline, timelineEntryId, (entry) =>
          entry.kind === "recommendation"
            ? {
                ...entry,
                recommendationId: result.data.recommendation_id,
                emptyState: result.data.empty_state,
                items: result.data.items,
                fallbackMessage: result.data.fallback_message,
                status: result.data.empty_state ? "empty" : "ready",
                errorMessage: undefined,
              }
            : entry,
        );
      }

      return result.data;
    } catch (error) {
      if (timelineEntryId) {
        updateEntry(setTimeline, timelineEntryId, (entry) =>
          entry.kind === "recommendation"
            ? {
                ...entry,
                recommendationId: "failed",
                status: "load_failed",
                errorMessage: toErrorMessage(error),
              }
            : entry,
        );
      }
      appendSystemNotice(toErrorMessage(error), "error");
      return null;
    } finally {
      setPullPending(false);
    }
  }

  async function handleSend(text: string) {
    const trimmed = text.trim();
    if (!trimmed) {
      return;
    }

    if (trimmed === "/pull") {
      setInputValue("");
      await handlePull(2, { addToTimeline: true });
      return;
    }

    if (trimmed === "/brief") {
      setInputValue("");
      await loadBrief();
      return;
    }

    const entryId = makeId("user");
    appendEntry(setTimeline, {
      id: entryId,
      kind: "user",
      text: trimmed,
      status: "sending",
    });
    setInputValue("");
    setChatPending(true);

    try {
      const result = await bridgeClient.sendChatMessage({
        channel: "desktop_plugin",
        message_type: "text",
        text: trimmed,
        client_message_id: makeId("client-message"),
        occurred_at: new Date().toISOString(),
      });

      setStateSnapshot(result.data.state);
      setConnectionStatus("connected");
      setStateErrorMessage(null);
      setLastSuccessfulAt(Date.now());

      updateEntry(setTimeline, entryId, (entry) =>
        entry.kind === "user"
          ? {
              ...entry,
              status: "processing",
            }
          : entry,
      );

      appendEntry(setTimeline, {
        id: makeId("assistant"),
        kind: "assistant",
        text: result.data.assistant_reply,
        requestId: result.requestId,
        eventId: result.data.event_id,
      });

      await reconcileState(
        () => bridgeClient.getState(),
        (stateResult) => {
          setStateSnapshot(stateResult.data.state);
          setConnectionStatus("connected");
          setStateErrorMessage(null);
          setLastSuccessfulAt(Date.now());
          updateEntry(setTimeline, entryId, (entry) =>
            entry.kind === "user"
              ? {
                  ...entry,
                  status: "synced",
                }
              : entry,
          );
        },
        () => {
          updateEntry(setTimeline, entryId, (entry) =>
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
      updateEntry(setTimeline, entryId, (entry) =>
        entry.kind === "user"
          ? {
              ...entry,
              status: "failed",
              errorMessage: toErrorMessage(error),
            }
          : entry,
      );
      setConnectionStatus("disconnected");
    } finally {
      setChatPending(false);
    }
  }

  async function handleRetry(entryId: string) {
    const entry = timeline.find((item) => item.id === entryId);
    if (!entry || entry.kind !== "user") {
      return;
    }

    updateEntry(setTimeline, entryId, (current) =>
      current.kind === "user"
        ? {
            ...current,
            status: "sending",
            errorMessage: undefined,
          }
        : current,
    );

    setChatPending(true);
    try {
      const result = await bridgeClient.sendChatMessage({
        channel: "desktop_plugin",
        message_type: "text",
        text: entry.text,
        client_message_id: makeId("client-message"),
        occurred_at: new Date().toISOString(),
      });

      setStateSnapshot(result.data.state);
      setConnectionStatus("connected");
      setStateErrorMessage(null);
      setLastSuccessfulAt(Date.now());
      updateEntry(setTimeline, entryId, (current) =>
        current.kind === "user"
          ? {
              ...current,
              status: "processing",
            }
          : current,
      );

      appendEntry(setTimeline, {
        id: makeId("assistant"),
        kind: "assistant",
        text: result.data.assistant_reply,
        requestId: result.requestId,
        eventId: result.data.event_id,
      });

      await reconcileState(
        () => bridgeClient.getState(),
        (stateResult) => {
          setStateSnapshot(stateResult.data.state);
          setConnectionStatus("connected");
          setStateErrorMessage(null);
          setLastSuccessfulAt(Date.now());
          updateEntry(setTimeline, entryId, (current) =>
            current.kind === "user"
              ? {
                  ...current,
                  status: "synced",
                }
              : current,
          );
        },
        () => {
          updateEntry(setTimeline, entryId, (current) =>
            current.kind === "user"
              ? {
                  ...current,
                  status: "synced",
                }
              : current,
          );
        },
      );
    } catch (error) {
      updateEntry(setTimeline, entryId, (current) =>
        current.kind === "user"
          ? {
              ...current,
              status: "failed",
              errorMessage: toErrorMessage(error),
            }
          : current,
      );
    } finally {
      setChatPending(false);
    }
  }

  async function handleRecommendationFeedback(
    recommendationId: string,
    nodeId: string | null,
    feedback: RecommendationFeedbackType,
  ) {
    updateRecommendationEntries(setTimeline, recommendationId, "feedback_submitting");

    try {
      await bridgeClient.submitFeedback(recommendationId, {
        feedback,
        node_id: nodeId,
        channel: "desktop_plugin",
      });

      updateRecommendationEntries(setTimeline, recommendationId, "feedback_done");

      if (feedback === "dismissed") {
        await handlePull(1, { addToTimeline: true });
      } else {
        appendSystemNotice(`Feedback recorded: ${feedback}.`);
      }

      void refreshState({ silent: true });
      if (isBriefOpen) {
        void loadBrief({ silent: true });
      }
    } catch (error) {
      updateRecommendationEntries(setTimeline, recommendationId, "feedback_failed", toErrorMessage(error));
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  async function handleSaveConfig() {
    setSettingsSaving(true);
    setPingResult(null);
    try {
      const saved = await bridgeClient.saveConfig(configDraft);
      setConfigDraft(saved);
      setSettingsMessage("Settings saved.");
    } catch (error) {
      setSettingsMessage(toErrorMessage(error));
    } finally {
      setSettingsSaving(false);
    }
  }

  async function handlePingBackend() {
    setPinging(true);
    setSettingsMessage(null);
    try {
      const result = await bridgeClient.pingBackend();
      setPingResult(result);
    } catch (error) {
      setPingResult(null);
      setSettingsMessage(toErrorMessage(error));
    } finally {
      setPinging(false);
    }
  }

  useEffect(() => {
    let active = true;
    void (async () => {
      const config = await bridgeClient.getConfig();
      if (!active) {
        return;
      }
      setConfigDraft(config);
      await refreshState();
    })();

    const unsubscribe = bridgeClient.subscribeLaunchContext?.((context) => {
      setLaunchContext(context);
    });

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refreshState({ silent: true });
      }
    }, 20_000);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (launchContext.launchId <= processedLaunchIdRef.current) {
      return;
    }

    processedLaunchIdRef.current = launchContext.launchId;
    const nextInput = extractLaunchText(launchContext);
    if (nextInput) {
      setInputValue(nextInput);
    }
    if (hasImagePayload(launchContext)) {
      appendSystemNotice("已收到图片，暂未解析。");
    }
    if (launchContext.code === "pull") {
      void handlePull(2, { addToTimeline: true });
      return;
    }
    if (launchContext.code === "brief") {
      void loadBrief();
    }
  }, [launchContext]);

  return (
    <div className="app-shell">
      <StatePanel
        state={stateSnapshot}
        loading={loadingState}
        connectionStatus={connectionStatus}
        errorMessage={stateErrorMessage}
        lastSuccessfulAt={lastSuccessfulAt}
        onOpenSettings={() => {
          setSettingsMessage(null);
          setPingResult(null);
          setSettingsOpen(true);
        }}
      />

      {latestRecommendation ? (
        <section className="panel latest-panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title panel-title-small">Latest Recommendation</h2>
              <p className="panel-subtitle">recommendation_id: {latestRecommendation.recommendation_id}</p>
            </div>
          </div>
          {latestRecommendation.empty_state ? (
            <p>{latestRecommendation.fallback_message ?? "No strong candidate right now."}</p>
          ) : (
            latestRecommendation.items.map((item) => (
              <article key={item.node_id} className="latest-item">
                <strong>{item.title}</strong>
                <p>{item.message}</p>
              </article>
            ))
          )}
        </section>
      ) : null}

      <Timeline
        entries={timeline}
        onRetryMessage={handleRetry}
        onRecommendationFeedback={handleRecommendationFeedback}
      />

      <InputPanel
        value={inputValue}
        disabled={busy}
        onChange={setInputValue}
        onSend={handleSend}
        onPull={async () => {
          await handlePull(2, { addToTimeline: true });
        }}
        onBrief={async () => {
          await loadBrief();
        }}
        onQuickFill={setInputValue}
      />

      <BriefDrawer
        open={isBriefOpen}
        loading={briefLoading}
        brief={brief}
        onClose={() => setBriefOpen(false)}
        onRefresh={async () => {
          await loadBrief();
        }}
      />
      <SettingsDrawer
        open={isSettingsOpen}
        configDraft={configDraft}
        pingResult={pingResult}
        statusMessage={settingsMessage}
        saving={settingsSaving}
        pinging={pinging}
        onClose={() => setSettingsOpen(false)}
        onChange={(field, value) => {
          setSettingsMessage(null);
          setPingResult(null);
          setConfigDraft((current) => ({
            ...current,
            [field]: field === "authToken" ? value || null : value,
          }));
        }}
        onSave={handleSaveConfig}
        onPing={handlePingBackend}
      />
    </div>
  );
}
