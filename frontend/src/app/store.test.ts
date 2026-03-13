import "../test/setup";

import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "./store";

describe("app store debug history", () => {
  beforeEach(() => {
    useAppStore.getState().resetForTests();
  });

  it("keeps only the latest five debug events in newest-first order", () => {
    for (let index = 0; index < 6; index += 1) {
      useAppStore.getState().logDebugEvent({
        label: `event-${index}`,
        requestId: `req-${index}`,
        eventId: null,
        recommendationId: null,
        response: { index },
        createdAt: `2026-03-13T10:0${index}:00Z`,
      });
    }

    const state = useAppStore.getState();
    expect(state.lastDebugEvent?.label).toBe("event-5");
    expect(state.debugEvents).toHaveLength(5);
    expect(state.debugEvents.map((event) => event.label)).toEqual([
      "event-5",
      "event-4",
      "event-3",
      "event-2",
      "event-1",
    ]);
  });
});
