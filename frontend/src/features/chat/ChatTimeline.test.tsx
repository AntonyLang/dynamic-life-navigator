import "../../test/setup";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatTimeline } from "./ChatTimeline";

describe("ChatTimeline recommendation states", () => {
  it("disables recommendation feedback buttons while feedback is submitting", () => {
    render(
      <ChatTimeline
        entries={[
          {
            id: "rec-entry-1",
            kind: "recommendation",
            recommendationId: "rec-1",
            emptyState: false,
            fallbackMessage: null,
            status: "feedback_submitting",
            items: [
              {
                node_id: "node-1",
                title: "Protect focus block",
                message: "Keep one uninterrupted hour.",
                reason_tags: ["state_match"],
              },
            ],
          },
        ]}
        onRetryMessage={vi.fn()}
        onRecommendationFeedback={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Snooze" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Swap" })).toBeDisabled();
  });

  it("renders distinct messages for load and feedback failures", () => {
    const { rerender } = render(
      <ChatTimeline
        entries={[
          {
            id: "rec-entry-1",
            kind: "recommendation",
            recommendationId: "rec-1",
            emptyState: false,
            fallbackMessage: null,
            status: "load_failed",
            errorMessage: "Request timed out.",
            items: [],
          },
        ]}
        onRetryMessage={vi.fn()}
        onRecommendationFeedback={vi.fn()}
      />,
    );

    expect(screen.getByText("Recommendation pull failed: Request timed out.")).toBeInTheDocument();

    rerender(
      <ChatTimeline
        entries={[
          {
            id: "rec-entry-2",
            kind: "recommendation",
            recommendationId: "rec-2",
            emptyState: false,
            fallbackMessage: null,
            status: "feedback_failed",
            errorMessage: "Request failed.",
            items: [
              {
                node_id: "node-2",
                title: "Review the roadmap",
                message: "Use the calmer option instead.",
                reason_tags: ["alternate"],
              },
            ],
          },
        ]}
        onRetryMessage={vi.fn()}
        onRecommendationFeedback={vi.fn()}
      />,
    );

    expect(screen.getByText("Feedback could not be recorded. Try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).not.toBeDisabled();
  });
});
