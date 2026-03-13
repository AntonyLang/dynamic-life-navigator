import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../lib/api/client";
import type { ActionNodeCreateRequest, ApiSuccess, StateResponse } from "../../lib/api/types";
import { toErrorMessage } from "./flowUtils";

interface UseDevActionsOptions {
  appendSystemNotice: (text: string, tone?: "info" | "error") => void;
  writeDebugEvent: (
    label: string,
    response: unknown,
    extras?: { requestId?: string | null; eventId?: string | null; recommendationId?: string | null },
  ) => void;
  isBriefOpen: boolean;
  refreshRecommendationsSilently: () => Promise<unknown> | void;
}

export function useDevActions({
  appendSystemNotice,
  writeDebugEvent,
  isBriefOpen,
  refreshRecommendationsSilently,
}: UseDevActionsOptions) {
  const queryClient = useQueryClient();

  const resetMutation = useMutation({
    mutationFn: apiClient.resetState,
  });

  const createNodeMutation = useMutation({
    mutationFn: apiClient.createNode,
  });

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
      await refreshRecommendationsSilently();
      writeDebugEvent("state.reset", result.data, {
        requestId: result.requestId,
      });
      appendSystemNotice("State reset completed.");
    } catch (error) {
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  async function handleCreateNode(payload: ActionNodeCreateRequest) {
    try {
      const result = await createNodeMutation.mutateAsync(payload);
      if (isBriefOpen) {
        void queryClient.invalidateQueries({ queryKey: ["brief"] });
      }
      await refreshRecommendationsSilently();
      writeDebugEvent("nodes.create", result.data, {
        requestId: result.requestId,
      });
      appendSystemNotice(`Node created: ${result.data.node.title}.`);
    } catch (error) {
      appendSystemNotice(toErrorMessage(error), "error");
    }
  }

  return {
    handleResetState,
    handleCreateNode,
    isDevActionPending: resetMutation.isPending || createNodeMutation.isPending,
  };
}
