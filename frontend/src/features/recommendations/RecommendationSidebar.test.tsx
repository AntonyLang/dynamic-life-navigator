import "../../test/setup";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RecommendationSidebar } from "./RecommendationSidebar";

describe("RecommendationSidebar", () => {
  it("renders fallback content and forwards quick prefills", async () => {
    const user = userEvent.setup();
    const onPrefill = vi.fn();

    render(
      <RecommendationSidebar
        recommendation={{
          request_id: "req-1",
          recommendation_id: "rec-1",
          mode: "pull",
          items: [],
          empty_state: true,
          fallback_message: "No good fit right now.",
        }}
        loading={false}
        onPull={vi.fn()}
        onPrefill={onPrefill}
      />,
    );

    expect(screen.getByText("No good fit right now.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Low mental load" }));

    expect(onPrefill).toHaveBeenCalledWith("Only show things that do not require much mental energy.");
  });
});
