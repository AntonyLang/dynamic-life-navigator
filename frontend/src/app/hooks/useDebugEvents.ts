import { useAppStore } from "../store";

interface DebugEventExtras {
  requestId?: string | null;
  eventId?: string | null;
  recommendationId?: string | null;
}

export function useDebugEvents() {
  const logDebugEvent = useAppStore((state) => state.logDebugEvent);

  function writeDebugEvent(label: string, response: unknown, extras?: DebugEventExtras) {
    logDebugEvent({
      label,
      requestId: extras?.requestId ?? null,
      eventId: extras?.eventId ?? null,
      recommendationId: extras?.recommendationId ?? null,
      response,
      createdAt: new Date().toISOString(),
    });
  }

  return {
    writeDebugEvent,
  };
}
