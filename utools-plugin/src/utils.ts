import { BridgeError } from "./bridge";
import type { BridgeSuccess, StateResponse } from "./types";

export const STATE_STALE_THRESHOLD_MS = 60_000;

export function makeId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function reconcileState(
  fetchState: () => Promise<BridgeSuccess<StateResponse>>,
  onSuccess: (result: BridgeSuccess<StateResponse>) => void,
  onExhausted: () => void,
) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await sleep(400);
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

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function toErrorMessage(error: unknown) {
  if (error instanceof BridgeError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed. Please try again.";
}

export function isStateStale(lastSuccessfulAt: number | null, now: number) {
  if (lastSuccessfulAt === null) {
    return false;
  }
  return now - lastSuccessfulAt > STATE_STALE_THRESHOLD_MS;
}
