import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAppStore, type RecommendationTimelineStatus } from "../store";
import { apiClient } from "../../lib/api/client";
import type { RecommendationFeedbackRequest } from "../../lib/api/types";
import { makeId, toErrorMessage } from "./flowUtils";

interface UseRecommendationFlowOptions {
  appendSystemNotice: (text: string, tone?: "info" | "error") => void;
  writeDebugEvent: (
    label: string,
    response: unknown,
    extras?: { requestId?: string | null; eventId?: string | null; recommendationId?: string | null },
  ) => void;
  isBriefOpen: boolean;
}

export function useRecommendationFlow({
  appendSystemNotice,
  writeDebugEvent,
  isBriefOpen,
}: UseRecommendationFlowOptions) {
  const queryClient = useQueryClient();
  const appendEntry = useAppStore((state) => state.appendEntry);
  const updateEntry = useAppStore((state) => state.updateEntry);
  const setLatestRecommendation = useAppStore((state) => state.setLatestRecommendation);

  const pullMutation = useMutation({
    mutationFn: (limit: number) => apiClient.pullRecommendation(limit),
  });

  const feedbackMutation = useMutation({
    mutationFn: (payload: { recommendationId: string; body: RecommendationFeedbackRequest }) =>
      apiClient.submitFeedback(payload.recommendationId, payload.body),
  });

  function updateRecommendationEntries(
    recommendationId: string,
    status: RecommendationTimelineStatus,
    errorMessage?: string,
  ) {
    for (const entry of useAppStore.getState().timeline) {
      if (entry.kind === "recommendation" && entry.recommendationId === recommendationId) {
        updateEntry(entry.id, (current) =>
          current.kind === "recommendation"
            ? {
                ...current,
                status,
                errorMessage,
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
                errorMessage: undefined,
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
                emptyState: false,
                items: [],
                status: "load_failed",
                errorMessage: toErrorMessage(error),
              }
            : entry,
        );
      }
      appendSystemNotice(toErrorMessage(error), "error");
      return null;
    }
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
      updateRecommendationEntries(recommendationId, "feedback_failed", toErrorMessage(error));
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  return {
    handlePull,
    handleRecommendationFeedback,
    isPullPending: pullMutation.isPending,
  };
}
