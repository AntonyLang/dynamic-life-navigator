import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAppStore } from "../store";
import { apiClient } from "../../lib/api/client";
import type { ApiSuccess, ChatMessageRequest, StateResponse } from "../../lib/api/types";
import { makeId, reconcileState, toErrorMessage } from "./flowUtils";

interface UseChatFlowOptions {
  appendSystemNotice: (text: string, tone?: "info" | "error") => void;
  writeDebugEvent: (
    label: string,
    response: unknown,
    extras?: { requestId?: string | null; eventId?: string | null; recommendationId?: string | null },
  ) => void;
}

export function useChatFlow({ appendSystemNotice, writeDebugEvent }: UseChatFlowOptions) {
  const queryClient = useQueryClient();
  const appendEntry = useAppStore((state) => state.appendEntry);
  const updateEntry = useAppStore((state) => state.updateEntry);

  const chatMutation = useMutation({
    mutationFn: (payload: ChatMessageRequest) => apiClient.sendChatMessage(payload),
  });

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

  async function sendChatMessage(text: string) {
    const entryId = makeId("user");
    appendEntry({
      id: entryId,
      kind: "user",
      text,
      status: "sending",
    });

    await submitChatText(text, entryId);
  }

  async function retryChatMessage(entryId: string) {
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

  return {
    sendChatMessage,
    retryChatMessage,
    isChatPending: chatMutation.isPending,
  };
}
