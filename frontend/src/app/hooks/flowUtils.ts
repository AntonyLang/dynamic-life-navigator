import type { ApiSuccess, StateResponse } from "../../lib/api/types";
import { ApiError } from "../../lib/api/types";

export const STATE_STALE_THRESHOLD_MS = 60_000;

export function makeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function reconcileState(
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

export function toErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed. Please try again.";
}
