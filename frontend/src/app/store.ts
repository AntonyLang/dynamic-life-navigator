import { create } from "zustand";

import type { RecommendationBriefResponse, RecommendationItem, RecommendationPullResponse } from "../lib/api/types";

export type TimelineEntry =
  | {
      id: string;
      kind: "user";
      text: string;
      status: "sending" | "processing" | "synced" | "failed";
      errorMessage?: string;
    }
  | {
      id: string;
      kind: "assistant";
      text: string;
      requestId?: string | null;
      eventId?: string;
    }
  | {
      id: string;
      kind: "system";
      text: string;
      tone: "info" | "error";
    }
  | {
      id: string;
      kind: "recommendation";
      recommendationId: string;
      emptyState: boolean;
      items: RecommendationItem[];
      fallbackMessage: string | null;
      status: "loading" | "ready" | "empty" | "feedback_submitting" | "feedback_done" | "feedback_failed";
    };

export interface DebugEvent {
  label: string;
  requestId?: string | null;
  recommendationId?: string | null;
  eventId?: string | null;
  response: unknown;
  createdAt: string;
}

interface AppStore {
  inputValue: string;
  timeline: TimelineEntry[];
  latestRecommendation: RecommendationPullResponse | null;
  latestBrief: RecommendationBriefResponse | null;
  isBriefOpen: boolean;
  isDevOpen: boolean;
  lastDebugEvent: DebugEvent | null;
  setInputValue: (value: string) => void;
  appendEntry: (entry: TimelineEntry) => void;
  updateEntry: (id: string, updater: (entry: TimelineEntry) => TimelineEntry) => void;
  setLatestRecommendation: (recommendation: RecommendationPullResponse | null) => void;
  setLatestBrief: (brief: RecommendationBriefResponse | null) => void;
  setBriefOpen: (open: boolean) => void;
  setDevOpen: (open: boolean) => void;
  logDebugEvent: (event: DebugEvent) => void;
  resetForTests: () => void;
}

const initialState = {
  inputValue: "",
  timeline: [] as TimelineEntry[],
  latestRecommendation: null as RecommendationPullResponse | null,
  latestBrief: null as RecommendationBriefResponse | null,
  isBriefOpen: false,
  isDevOpen: true,
  lastDebugEvent: null as DebugEvent | null,
};

export const useAppStore = create<AppStore>((set) => ({
  ...initialState,
  setInputValue: (value) => set({ inputValue: value }),
  appendEntry: (entry) => set((state) => ({ timeline: [...state.timeline, entry] })),
  updateEntry: (id, updater) =>
    set((state) => ({
      timeline: state.timeline.map((entry) => (entry.id === id ? updater(entry) : entry)),
    })),
  setLatestRecommendation: (recommendation) => set({ latestRecommendation: recommendation }),
  setLatestBrief: (brief) => set({ latestBrief: brief }),
  setBriefOpen: (open) => set({ isBriefOpen: open }),
  setDevOpen: (open) => set({ isDevOpen: open }),
  logDebugEvent: (event) => set({ lastDebugEvent: event }),
  resetForTests: () => set(initialState),
}));
